from django.http import Http404
from django.shortcuts import get_object_or_404
from django_rq.queues import get_connection
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.routers import APIRootView
from rest_framework.viewsets import ModelViewSet
from rq import Worker

from extras import filtersets
from extras.jobs import ScriptJob
from extras.models import *
from netbox.api.authentication import IsAuthenticatedOrLoginNotRequired
from netbox.api.features import SyncedDataMixin
from netbox.api.metadata import ContentTypeMetadata
from netbox.api.renderers import TextRenderer
from netbox.api.viewsets import BaseViewSet, NetBoxModelViewSet
from utilities.exceptions import RQWorkerNotRunningException
from utilities.request import copy_safe_request
from utilities.permissions import qs_filter_from_constraints, get_permission_for_model, permission_is_exempt
from . import serializers
from .mixins import ConfigTemplateRenderMixin


class ExtrasRootView(APIRootView):
    """
    Extras API root view
    """
    def get_view_name(self):
        return 'Extras'


#
# EventRules
#

class EventRuleViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = EventRule.objects.all()
    serializer_class = serializers.EventRuleSerializer
    filterset_class = filtersets.EventRuleFilterSet


#
# Webhooks
#

class WebhookViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = Webhook.objects.all()
    serializer_class = serializers.WebhookSerializer
    filterset_class = filtersets.WebhookFilterSet


#
# Custom fields
#

class CustomFieldViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = CustomField.objects.select_related('choice_set')
    serializer_class = serializers.CustomFieldSerializer
    filterset_class = filtersets.CustomFieldFilterSet


class CustomFieldChoiceSetViewSet(NetBoxModelViewSet):
    queryset = CustomFieldChoiceSet.objects.all()
    serializer_class = serializers.CustomFieldChoiceSetSerializer
    filterset_class = filtersets.CustomFieldChoiceSetFilterSet

    @action(detail=True)
    def choices(self, request, pk):
        """
        Provides an endpoint to iterate through each choice in a set.
        """
        choiceset = get_object_or_404(self.queryset, pk=pk)
        choices = choiceset.choices

        # Enable filtering
        if q := request.GET.get('q'):
            q = q.lower()
            choices = [c for c in choices if q in c[0].lower() or q in c[1].lower()]

        # Paginate data
        if page := self.paginate_queryset(choices):
            data = [
                {'id': c[0], 'display': c[1]} for c in page
            ]
        else:
            data = []

        return self.get_paginated_response(data)


#
# Custom links
#

class CustomLinkViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = CustomLink.objects.all()
    serializer_class = serializers.CustomLinkSerializer
    filterset_class = filtersets.CustomLinkFilterSet


#
# Export templates
#

class ExportTemplateViewSet(SyncedDataMixin, NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = ExportTemplate.objects.all()
    serializer_class = serializers.ExportTemplateSerializer
    filterset_class = filtersets.ExportTemplateFilterSet


#
# Saved filters
#

class SavedFilterViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = SavedFilter.objects.all()
    serializer_class = serializers.SavedFilterSerializer
    filterset_class = filtersets.SavedFilterFilterSet


#
# Table Configs
#

class TableConfigViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = TableConfig.objects.all()
    serializer_class = serializers.TableConfigSerializer
    filterset_class = filtersets.TableConfigFilterSet


#
# Bookmarks
#

from django.core.exceptions import PermissionDenied
from utilities.permissions import get_permission_for_model

class BookmarkViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = Bookmark.objects.all()
    serializer_class = serializers.BookmarkSerializer
    filterset_class = filtersets.BookmarkFilterSet

    def _explicit_constraints(self, user, action):
        from core.models import ObjectType
        from users.models import ObjectPermission
        if not (user and user.is_authenticated):
            return []
        try:
            ot = ObjectType.objects.get_for_model(Bookmark)
        except Exception:
            return []
        perms = ObjectPermission.objects.filter(
            enabled=True,
            users=user,
            actions__contains=[action],
            object_types=ot,
        )
        # Flatten all constraint sets from all matching ObjectPermissions
        constraints = []
        for p in perms:
            constraints.extend(p.list_constraints())
        return constraints

    def get_queryset(self):
        # Build queryset strictly from explicit ObjectPermissions (ignore DEFAULT_PERMISSIONS)
        # Start from base manager to bypass BaseViewSet.initial() restriction logic
        qs = Bookmark.objects.all()
        user = getattr(self.request, 'user', None)
        method = getattr(self.request, 'method', 'GET')
        # For safe reads, enforce explicit 'view' constraints
        if method in ('GET', 'HEAD', 'OPTIONS'):
            # If view permission is exempt (anonymous read allowed), return full queryset
            view_perm = get_permission_for_model(Bookmark, 'view')
            if permission_is_exempt(view_perm):
                return qs
            constraints = self._explicit_constraints(user, 'view')
            if not constraints:
                return qs.none()
            q = qs_filter_from_constraints(constraints, tokens={'$user': user})
            return qs.filter(q)
        # For unsafe methods, allow retrieval; per-action checks happen in create/destroy overrides
        return qs

    def retrieve(self, request, *args, **kwargs):
        # Return 403 if user lacks explicit 'view' permission instead of 404
        view_perm = get_permission_for_model(Bookmark, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        view_perm = get_permission_for_model(Bookmark, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        # Require explicit ObjectPermission('add') for Bookmark
        if not self._explicit_constraints(request.user, 'add'):
            raise PermissionDenied()
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Require explicit ObjectPermission('delete') for Bookmark
        if not self._explicit_constraints(request.user, 'delete'):
            raise PermissionDenied()
        return super().destroy(request, *args, **kwargs)

    def get_bulk_destroy_queryset(self):
        # Use delete constraints for bulk deletion instead of view constraints
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        constraints = self._explicit_constraints(user, 'delete')
        if not constraints:
            return qs.none()
        q = qs_filter_from_constraints(constraints, tokens={'$user': user})
        return qs.filter(q)


#
# Notifications & subscriptions
#

class NotificationViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = Notification.objects.all()
    serializer_class = serializers.NotificationSerializer

    def _explicit_constraints(self, user, action):
        from core.models import ObjectType
        from users.models import ObjectPermission
        if not (user and user.is_authenticated):
            return []
        try:
            ot = ObjectType.objects.get_for_model(Notification)
        except Exception:
            return []
        perms = ObjectPermission.objects.filter(
            enabled=True,
            users=user,
            actions__contains=[action],
            object_types=ot,
        )
        constraints = []
        for p in perms:
            constraints.extend(p.list_constraints())
        return constraints

    def get_queryset(self):
        qs = Notification.objects.all()
        user = getattr(self.request, 'user', None)
        method = getattr(self.request, 'method', 'GET')
        if method in ('GET', 'HEAD', 'OPTIONS'):
            view_perm = get_permission_for_model(Notification, 'view')
            if permission_is_exempt(view_perm):
                return qs
            constraints = self._explicit_constraints(user, 'view')
            if not constraints:
                return qs.none()
            q = qs_filter_from_constraints(constraints, tokens={'$user': user})
            return qs.filter(q)
        return qs

    def retrieve(self, request, *args, **kwargs):
        view_perm = get_permission_for_model(Notification, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        view_perm = get_permission_for_model(Notification, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().list(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # Enforce explicit change permission before resolving the object
        if not self._explicit_constraints(request.user, 'change'):
            raise PermissionDenied()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._explicit_constraints(request.user, 'delete'):
            raise PermissionDenied()
        return super().destroy(request, *args, **kwargs)


class NotificationGroupViewSet(NetBoxModelViewSet):
    queryset = NotificationGroup.objects.all()
    serializer_class = serializers.NotificationGroupSerializer


class SubscriptionViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = Subscription.objects.all()
    serializer_class = serializers.SubscriptionSerializer

    def _explicit_constraints(self, user, action):
        from core.models import ObjectType
        from users.models import ObjectPermission
        if not (user and user.is_authenticated):
            return []
        try:
            ot = ObjectType.objects.get_for_model(Subscription)
        except Exception:
            return []
        perms = ObjectPermission.objects.filter(
            enabled=True,
            users=user,
            actions__contains=[action],
            object_types=ot,
        )
        constraints = []
        for p in perms:
            constraints.extend(p.list_constraints())
        return constraints

    def get_queryset(self):
        qs = Subscription.objects.all()
        user = getattr(self.request, 'user', None)
        method = getattr(self.request, 'method', 'GET')
        if method in ('GET', 'HEAD', 'OPTIONS'):
            view_perm = get_permission_for_model(Subscription, 'view')
            if permission_is_exempt(view_perm):
                return qs
            constraints = self._explicit_constraints(user, 'view')
            if not constraints:
                return qs.none()
            q = qs_filter_from_constraints(constraints, tokens={'$user': user})
            return qs.filter(q)
        return qs

    def retrieve(self, request, *args, **kwargs):
        view_perm = get_permission_for_model(Subscription, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        view_perm = get_permission_for_model(Subscription, 'view')
        if not permission_is_exempt(view_perm) and not self._explicit_constraints(request.user, 'view'):
            raise PermissionDenied()
        return super().list(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self._explicit_constraints(request.user, 'change'):
            raise PermissionDenied()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._explicit_constraints(request.user, 'delete'):
            raise PermissionDenied()
        return super().destroy(request, *args, **kwargs)


#
# Tags
#

class TagViewSet(NetBoxModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = serializers.TagSerializer
    filterset_class = filtersets.TagFilterSet


class TaggedItemViewSet(RetrieveModelMixin, ListModelMixin, BaseViewSet):
    queryset = TaggedItem.objects.prefetch_related(
        'content_type', 'content_object', 'tag'
    ).order_by('tag__weight', 'tag__name')
    serializer_class = serializers.TaggedItemSerializer
    filterset_class = filtersets.TaggedItemFilterSet


#
# Image attachments
#

class ImageAttachmentViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = ImageAttachment.objects.all()
    serializer_class = serializers.ImageAttachmentSerializer
    filterset_class = filtersets.ImageAttachmentFilterSet


#
# Journal entries
#

class JournalEntryViewSet(NetBoxModelViewSet):
    metadata_class = ContentTypeMetadata
    queryset = JournalEntry.objects.all()
    serializer_class = serializers.JournalEntrySerializer
    filterset_class = filtersets.JournalEntryFilterSet


#
# Config contexts
#

class ConfigContextProfileViewSet(SyncedDataMixin, NetBoxModelViewSet):
    queryset = ConfigContextProfile.objects.all()
    serializer_class = serializers.ConfigContextProfileSerializer
    filterset_class = filtersets.ConfigContextProfileFilterSet


class ConfigContextViewSet(SyncedDataMixin, NetBoxModelViewSet):
    queryset = ConfigContext.objects.all()
    serializer_class = serializers.ConfigContextSerializer
    filterset_class = filtersets.ConfigContextFilterSet


#
# Config templates
#

class ConfigTemplateViewSet(SyncedDataMixin, ConfigTemplateRenderMixin, NetBoxModelViewSet):
    queryset = ConfigTemplate.objects.all()
    serializer_class = serializers.ConfigTemplateSerializer
    filterset_class = filtersets.ConfigTemplateFilterSet

    @action(detail=True, methods=['post'], renderer_classes=[JSONRenderer, TextRenderer])
    def render(self, request, pk):
        """
        Render a ConfigTemplate using the context data provided (if any). If the client requests "text/plain" data,
        return the raw rendered content, rather than serialized JSON.
        """
        configtemplate = self.get_object()
        context = request.data

        return self.render_configtemplate(request, configtemplate, context)


#
# Scripts
#

@extend_schema_view(
    update=extend_schema(request=serializers.ScriptInputSerializer),
    partial_update=extend_schema(request=serializers.ScriptInputSerializer),
)
class ScriptViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrLoginNotRequired]
    queryset = Script.objects.all()
    serializer_class = serializers.ScriptSerializer
    filterset_class = filtersets.ScriptFilterSet

    _ignore_model_permissions = True
    lookup_value_regex = '[^/]+'  # Allow dots

    def _get_script(self, pk):
        # If pk is numeric, retrieve script by ID
        if pk.isnumeric():
            return get_object_or_404(self.queryset, pk=pk)

        # Default to retrieval by module & name
        try:
            module_name, script_name = pk.split('.', maxsplit=1)
        except ValueError:
            raise Http404

        return get_object_or_404(self.queryset, module__file_path=f'{module_name}.py', name=script_name)

    def retrieve(self, request, pk):
        script = self._get_script(pk)
        serializer = serializers.ScriptDetailSerializer(script, context={'request': request})

        return Response(serializer.data)

    def post(self, request, pk):
        """
        Run a Script identified by its numeric PK or module & name and return the pending Job as the result
        """
        if not request.user.has_perm('extras.run_script'):
            raise PermissionDenied("This user does not have permission to run scripts.")

        script = self._get_script(pk)
        input_serializer = serializers.ScriptInputSerializer(
            data=request.data,
            context={'script': script}
        )

        # Check that at least one RQ worker is running
        if not Worker.count(get_connection('default')):
            raise RQWorkerNotRunningException()

        if input_serializer.is_valid():
            ScriptJob.enqueue(
                instance=script,
                user=request.user,
                data=input_serializer.data['data'],
                request=copy_safe_request(request),
                commit=input_serializer.data['commit'],
                job_timeout=script.python_class.job_timeout,
                schedule_at=input_serializer.validated_data.get('schedule_at'),
                interval=input_serializer.validated_data.get('interval')
            )
            serializer = serializers.ScriptDetailSerializer(script, context={'request': request})

            return Response(serializer.data)

        return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


#
# User dashboard
#

class DashboardView(RetrieveUpdateDestroyAPIView):
    queryset = Dashboard.objects.all()
    serializer_class = serializers.DashboardSerializer

    def get_object(self):
        return Dashboard.objects.filter(user=self.request.user).first()
