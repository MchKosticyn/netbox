from django.db.models import Manager

from ipam.lookups import Host, Inet
from utilities.querysets import RestrictedQuerySet

from ipam.querysets import PrefixQuerySet


class IPAddressManager(Manager.from_queryset(RestrictedQuerySet)):

    def get_queryset(self):
        """
        Order IPs by family and host (ignoring mask), using SQLite UDFs HOST/INET.
        """
        return super().get_queryset().order_by(Inet(Host('address')))


class PrefixManager(Manager.from_queryset(PrefixQuerySet)):

    def get_queryset(self):
        """
        Order by VRF (NULLs first), then by family/network key, then by mask length, then pk.
        INET(prefix) provides a family + canonical key for the network address; MASKLEN(prefix) for prefix length.
        """
        from django.db.models import F
        return (
            super()
            .get_queryset()
            .order_by(F('vrf').asc(nulls_first=True), Inet('prefix'), 'prefix__net_mask_length', 'pk')
        )
