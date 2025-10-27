from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
# Avoid global import of ContentType at module import time; import where needed at runtime

from django.db import models
from utilities.json import CustomFieldJSONEncoder

# Pure SQLite codebase: remove all Postgres range/array imports

class NumericRange:
    """Lightweight NumericRange replacement for SQLite-based storage.

    Stored representation is expected to be a dict/list in the DB (JSON). This
    class provides convenience attributes used by the application code.
    """

    def __init__(self, lower, upper, bounds='[)'):
        self.lower = int(lower)
        self.upper = int(upper)
        # bounds is a string like '[]' or '[)' etc.
        self.lower_inc = bounds.startswith('[')
        self.upper_inc = bounds.endswith(']')
        self.bounds = bounds

    def __repr__(self):
        return f"NumericRange({self.lower}, {self.upper}, bounds='{self.bounds}')"

    def __contains__(self, item):
        if item is None:
            return False
        if self.lower_inc:
            lower_ok = item >= self.lower
        else:
            lower_ok = item > self.lower
        if self.upper_inc:
            upper_ok = item <= self.upper
        else:
            upper_ok = item < self.upper
        return lower_ok and upper_ok

    def __eq__(self, other):
        # Support equality comparison with both local NumericRange and utilities.data.NumericRange
        if not hasattr(other, 'lower'):
            return NotImplemented
        return (
            int(self.lower) == int(other.lower) and
            int(self.upper) == int(other.upper) and
            bool(getattr(self, 'lower_inc', str(getattr(self, 'bounds', '[)')).startswith('['))) == bool(getattr(other, 'lower_inc', str(getattr(other, 'bounds', '[)')).startswith('['))) and
            bool(getattr(self, 'upper_inc', str(getattr(self, 'bounds', '[)')).endswith(']'))) == bool(getattr(other, 'upper_inc', str(getattr(other, 'bounds', '[)')).endswith(']')))
        )



from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _

from dcim.models import Interface, Site, SiteGroup
from ipam.choices import *
from ipam.constants import *
from ipam.querysets import VLANGroupQuerySet, VLANQuerySet
from netbox.models import OrganizationalModel, PrimaryModel, NetBoxModel
from utilities.data import check_ranges_overlap, ranges_to_string, ranges_to_string_list
from virtualization.models import VMInterface

__all__ = (
    'VLAN',
    'VLANGroup',
    'VLANTranslationPolicy',
    'VLANTranslationRule',
)


def default_vid_ranges():
    """Return the default VID ranges as a JSON-serializable structure for SQLite.

    Use half-open intervals [lower, upper) to match PostgreSQL int4range semantics.
    """
    return [{
        'lower': VLAN_VID_MIN,
        'upper': VLAN_VID_MAX + 1,
        'bounds': '[)',
    }]


class VLANGroup(OrganizationalModel):
    """
    A VLAN group is an arbitrary collection of VLANs within which VLAN IDs and names must be unique. Each group must
     define one or more ranges of valid VLAN IDs, and may be assigned a specific scope.
    """
    name = models.CharField(
        verbose_name=_('name'),
        max_length=100,
        # SQLite does not support this collation; keep attribute for Postgres via migrations only
        # db_collation omitted under SQLite: natural_sort
    )
    slug = models.SlugField(
        verbose_name=_('slug'),
        max_length=100
    )
    scope_type = models.ForeignKey(
        to='contenttypes.ContentType',
        on_delete=models.CASCADE,
        blank=True,
        null=True
    )
    scope_id = models.PositiveBigIntegerField(
        blank=True,
        null=True
    )
    scope = GenericForeignKey(
        ct_field='scope_type',
        fk_field='scope_id'
    )
    # SQLite-only: store VLAN ID ranges as JSON; previously Postgres int4range[]
    vid_ranges = models.JSONField(
        verbose_name=_('VLAN ID ranges'),
        default=default_vid_ranges,
        encoder=CustomFieldJSONEncoder,
    )

    def __setattr__(self, name, value):
        # Normalize vid_ranges assignments eagerly so bulk_create() works with JSONField
        if name == 'vid_ranges' and value is not None:
            try:
                value = [self._range_to_json(v) for v in value]
            except Exception:
                # Leave as-is; validation will catch improper values later
                pass
        super().__setattr__(name, value)

    # --- Helpers to normalize vid_ranges between JSON (DB) and objects (logic) ---
    @staticmethod
    def _range_to_obj(r):
        """Convert JSON dict or compatible object to a NumericRange instance."""
        if r is None:
            return None
        if isinstance(r, NumericRange):
            return r
        if isinstance(r, dict):
            lower = r.get('lower')
            upper = r.get('upper')
            bounds = r.get('bounds', '[)')
            return NumericRange(lower, upper, bounds)
        # Fallback: duck-typing object with lower/upper and maybe bounds
        if hasattr(r, 'lower') and hasattr(r, 'upper'):
            bounds = getattr(r, 'bounds', '[)')
            return NumericRange(r.lower, r.upper, bounds)
        raise TypeError('Unsupported VLAN range representation: %r' % (r,))

    @staticmethod
    def _range_to_json(r):
        """Convert NumericRange or compatible object to JSON-serializable dict."""
        if r is None:
            return None
        if isinstance(r, dict):
            return r
        # Derive bounds string if not present
        bounds = getattr(r, 'bounds', '[)' )
        if not isinstance(bounds, str):
            bounds = '[)' if getattr(r, 'lower_inc', True) and not getattr(r, 'upper_inc', False) else '[)'
        return {
            'lower': int(getattr(r, 'lower')),
            'upper': int(getattr(r, 'upper')),
            'bounds': bounds,
        }

    def _vid_ranges_as_objects(self):
        return [self._range_to_obj(r) for r in (self.vid_ranges or [])]

    def _vid_ranges_as_json(self):
        return [self._range_to_json(r) for r in (self.vid_ranges or [])]
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='vlan_groups',
        blank=True,
        null=True
    )
    _total_vlan_ids = models.PositiveBigIntegerField(
        default=VLAN_VID_MAX - VLAN_VID_MIN + 1
    )

    objects = VLANGroupQuerySet.as_manager()

    class Meta:
        ordering = ('name', 'pk')  # Name may be non-unique
        indexes = (
            models.Index(fields=('scope_type', 'scope_id')),
        )
        constraints = (
            models.UniqueConstraint(
                fields=('scope_type', 'scope_id', 'name'),
                name='%(app_label)s_%(class)s_unique_scope_name'
            ),
            models.UniqueConstraint(
                fields=('scope_type', 'scope_id', 'slug'),
                name='%(app_label)s_%(class)s_unique_scope_slug'
            ),
        )
        verbose_name = _('VLAN group')
        verbose_name_plural = _('VLAN groups')

    def clean(self):
        super().clean()

        # Validate scope assignment
        if self.scope_type and not self.scope_id:
            raise ValidationError(_("Cannot set scope_type without scope_id."))
        if self.scope_id and not self.scope_type:
            raise ValidationError(_("Cannot set scope_id without scope_type."))

        # Normalize to objects for validation logic
        ranges = self._vid_ranges_as_objects()

        # Validate VID ranges
        for vid_range in ranges:
            lower_vid = vid_range.lower if vid_range.lower_inc else vid_range.lower + 1
            upper_vid = vid_range.upper if vid_range.upper_inc else vid_range.upper - 1
            if lower_vid < VLAN_VID_MIN:
                raise ValidationError({
                    'vid_ranges': _("Starting VLAN ID in range ({value}) cannot be less than {minimum}").format(
                        value=lower_vid, minimum=VLAN_VID_MIN
                    )
                })
            if upper_vid > VLAN_VID_MAX:
                raise ValidationError({
                    'vid_ranges': _("Ending VLAN ID in range ({value}) cannot exceed {maximum}").format(
                        value=upper_vid, maximum=VLAN_VID_MAX
                    )
                })
            if lower_vid > upper_vid:
                raise ValidationError({
                    'vid_ranges': _(
                        "Ending VLAN ID in range must be greater than or equal to the starting VLAN ID ({range})"
                    ).format(range=f'{lower_vid}-{upper_vid}')
                })

        # Check for overlapping VID ranges
        if ranges and check_ranges_overlap(ranges):
            raise ValidationError({'vid_ranges': _("Ranges cannot overlap.")})

    def save(self, *args, **kwargs):
        # Compute total from object view
        ranges = self._vid_ranges_as_objects()
        self._total_vlan_ids = 0
        for vid_range in ranges:
            # NumericRange semantics are half-open [lower, upper) by default
            # but _total_vlan_ids historically counts inclusive range size.
            # For bounds '[)' => size = upper - lower; for others adjust.
            lower = vid_range.lower if vid_range.lower_inc else vid_range.lower + 1
            upper = vid_range.upper if vid_range.upper_inc else vid_range.upper - 1
            self._total_vlan_ids += (upper - lower + 1)

        # Ensure JSON-serializable representation is stored
        self.vid_ranges = [self._range_to_json(r) for r in ranges]

        super().save(*args, **kwargs)

    def get_available_vids(self):
        """
        Return all available VLANs within this group.
        """
        available_vlans = set()
        for vlan_range in self._vid_ranges_as_objects():
            # Treat ranges as half-open [lower, upper)
            available_vlans |= set(range(int(vlan_range.lower), int(vlan_range.upper)))
        available_vlans -= set(VLAN.objects.filter(group=self).values_list('vid', flat=True))

        return sorted(available_vlans)

    def get_next_available_vid(self):
        """
        Return the first available VLAN ID (1-4094) in the group.
        """
        available_vids = self.get_available_vids()
        if available_vids:
            return available_vids[0]
        return None

    def get_child_vlans(self):
        """
        Return all VLANs within this group.
        """
        return VLAN.objects.filter(group=self).order_by('vid')

    @property
    def vid_ranges_items(self):
        """
        Property that converts VID ranges to a list of string representations.
        """
        return ranges_to_string_list(self._vid_ranges_as_objects())

    @property
    def vid_ranges_list(self):
        """
        Property that converts VID ranges into a string representation.
        """
        return ranges_to_string(self._vid_ranges_as_objects())


class VLAN(PrimaryModel):
    """
    A VLAN is a distinct layer two forwarding domain identified by a 12-bit integer (1-4094). Each VLAN must be assigned
    to a Site, however VLAN IDs need not be unique within a Site. A VLAN may optionally be assigned to a VLANGroup,
    within which all VLAN IDs and names but be unique.

    Like Prefixes, each VLAN is assigned an operational status and optionally a user-defined Role. A VLAN can have zero
    or more Prefixes assigned to it.
    """
    site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='vlans',
        blank=True,
        null=True,
        help_text=_("The specific site to which this VLAN is assigned (if any)")
    )
    group = models.ForeignKey(
        to='ipam.VLANGroup',
        on_delete=models.PROTECT,
        related_name='vlans',
        blank=True,
        null=True,
        help_text=_("VLAN group (optional)")
    )
    vid = models.PositiveSmallIntegerField(
        verbose_name=_('VLAN ID'),
        validators=(
            MinValueValidator(VLAN_VID_MIN),
            MaxValueValidator(VLAN_VID_MAX)
        ),
        help_text=_("Numeric VLAN ID (1-4094)")
    )
    name = models.CharField(
        verbose_name=_('name'),
        max_length=64
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='vlans',
        blank=True,
        null=True
    )
    status = models.CharField(
        verbose_name=_('status'),
        max_length=50,
        choices=VLANStatusChoices,
        default=VLANStatusChoices.STATUS_ACTIVE,
        help_text=_("Operational status of this VLAN")
    )
    role = models.ForeignKey(
        to='ipam.Role',
        on_delete=models.SET_NULL,
        related_name='vlans',
        blank=True,
        null=True,
        help_text=_("The primary function of this VLAN")
    )
    qinq_svlan = models.ForeignKey(
        to='self',
        on_delete=models.PROTECT,
        related_name='qinq_cvlans',
        blank=True,
        null=True
    )
    qinq_role = models.CharField(
        verbose_name=_('Q-in-Q role'),
        max_length=50,
        choices=VLANQinQRoleChoices,
        blank=True,
        null=True,
        help_text=_("Customer/service VLAN designation (for Q-in-Q/IEEE 802.1ad)")
    )
    l2vpn_terminations = GenericRelation(
        to='vpn.L2VPNTermination',
        content_type_field='assigned_object_type',
        object_id_field='assigned_object_id',
        related_query_name='vlan'
    )

    objects = VLANQuerySet.as_manager()

    clone_fields = [
        'site', 'group', 'tenant', 'status', 'role', 'description', 'qinq_role', 'qinq_svlan',
    ]

    class Meta:
        ordering = ('site', 'group', 'vid', 'pk')  # (site, group, vid) may be non-unique
        constraints = (
            models.UniqueConstraint(
                fields=('group', 'vid'),
                name='%(app_label)s_%(class)s_unique_group_vid'
            ),
            models.UniqueConstraint(
                fields=('group', 'name'),
                name='%(app_label)s_%(class)s_unique_group_name'
            ),
            models.UniqueConstraint(
                fields=('qinq_svlan', 'vid'),
                name='%(app_label)s_%(class)s_unique_qinq_svlan_vid'
            ),
            models.UniqueConstraint(
                fields=('qinq_svlan', 'name'),
                name='%(app_label)s_%(class)s_unique_qinq_svlan_name'
            ),
        )
        verbose_name = _('VLAN')
        verbose_name_plural = _('VLANs')

    def __str__(self):
        return f'{self.name} ({self.vid})'

    def clean(self):
        super().clean()

        # Validate VLAN group (if assigned)
        from django.contrib.contenttypes.models import ContentType
        if self.group and self.site and self.group.scope_type == ContentType.objects.get_for_model(Site):
            if self.site != self.group.scope:
                raise ValidationError(
                    _(
                        "VLAN is assigned to group {group} (scope: {scope}); cannot also assign to site {site}."
                    ).format(group=self.group, scope=self.group.scope, site=self.site)
                )
        from django.contrib.contenttypes.models import ContentType
        if self.group and self.site and self.group.scope_type == ContentType.objects.get_for_model(SiteGroup):
            if self.site not in self.group.scope.sites.all():
                raise ValidationError(
                    _(
                        "The assigned site {site} is not a member of the assigned group {group} (scope: {scope})."
                    ).format(group=self.group, scope=self.group.scope, site=self.site)
                )

        # Check that the VLAN ID is permitted in the assigned group (if any)
        if self.group:
            # Under SQLite, vid_ranges is stored as JSON; normalize to NumericRange objects
            group_ranges = getattr(self.group, '_vid_ranges_as_objects', lambda: self.group.vid_ranges)()
            if not any(self.vid in r for r in group_ranges):
                raise ValidationError({
                    'vid': _(
                        "VID must be in ranges {ranges} for VLANs in group {group}"
                    ).format(ranges=ranges_to_string(group_ranges), group=self.group)
                })

        # Only Q-in-Q customer VLANs may be assigned to a service VLAN
        if self.qinq_svlan and self.qinq_role != VLANQinQRoleChoices.ROLE_CUSTOMER:
            raise ValidationError({
                'qinq_svlan': _("Only Q-in-Q customer VLANs maybe assigned to a service VLAN.")
            })

        # A Q-in-Q customer VLAN must be assigned to a service VLAN
        if self.qinq_role == VLANQinQRoleChoices.ROLE_CUSTOMER and not self.qinq_svlan:
            raise ValidationError({
                'qinq_role': _("A Q-in-Q customer VLAN must be assigned to a service VLAN.")
            })

    def get_status_color(self):
        return VLANStatusChoices.colors.get(self.status)

    def get_qinq_role_color(self):
        return VLANQinQRoleChoices.colors.get(self.qinq_role)

    def get_interfaces(self):
        # Return all device interfaces assigned to this VLAN
        return Interface.objects.filter(
            Q(untagged_vlan_id=self.pk) |
            Q(tagged_vlans=self.pk)
        ).distinct()

    def get_vminterfaces(self):
        # Return all VM interfaces assigned to this VLAN
        return VMInterface.objects.filter(
            Q(untagged_vlan_id=self.pk) |
            Q(tagged_vlans=self.pk)
        ).distinct()

    @property
    def l2vpn_termination(self):
        return self.l2vpn_terminations.first()


class VLANTranslationPolicy(PrimaryModel):
    name = models.CharField(
        verbose_name=_('name'),
        max_length=100,
        unique=True,
    )

    class Meta:
        verbose_name = _('VLAN translation policy')
        verbose_name_plural = _('VLAN translation policies')
        ordering = ('name',)

    def __str__(self):
        return self.name


class VLANTranslationRule(NetBoxModel):
    policy = models.ForeignKey(
        to=VLANTranslationPolicy,
        related_name='rules',
        on_delete=models.CASCADE,
    )
    description = models.CharField(
        verbose_name=_('description'),
        max_length=200,
        blank=True
    )
    local_vid = models.PositiveSmallIntegerField(
        verbose_name=_('Local VLAN ID'),
        validators=(
            MinValueValidator(VLAN_VID_MIN),
            MaxValueValidator(VLAN_VID_MAX)
        ),
        help_text=_("Numeric VLAN ID (1-4094)")
    )
    remote_vid = models.PositiveSmallIntegerField(
        verbose_name=_('Remote VLAN ID'),
        validators=(
            MinValueValidator(VLAN_VID_MIN),
            MaxValueValidator(VLAN_VID_MAX)
        ),
        help_text=_("Numeric VLAN ID (1-4094)")
    )
    prerequisite_models = (
        'ipam.VLANTranslationPolicy',
    )

    clone_fields = ['policy']

    class Meta:
        verbose_name = _('VLAN translation rule')
        ordering = ('policy', 'local_vid',)
        constraints = (
            models.UniqueConstraint(
                fields=('policy', 'local_vid'),
                name='%(app_label)s_%(class)s_unique_policy_local_vid'
            ),
            models.UniqueConstraint(
                fields=('policy', 'remote_vid'),
                name='%(app_label)s_%(class)s_unique_policy_remote_vid'
            ),
        )

    def __str__(self):
        return f'{self.local_vid} -> {self.remote_vid} ({self.policy})'

    def to_objectchange(self, action):
        objectchange = super().to_objectchange(action)
        objectchange.related_object = self.policy
        return objectchange
