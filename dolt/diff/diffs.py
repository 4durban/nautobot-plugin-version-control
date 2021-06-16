from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q, F, Subquery, OuterRef, Value

from nautobot.dcim.tables import cables, devices, devicetypes, power, racks, sites
from nautobot.circuits import tables as circuits_tables
from nautobot.ipam import tables as ipam_tables
from nautobot.tenancy import tables as tenancy_tables
from nautobot.virtualization import tables as virtualization_tables
from nautobot.utilities.querysets import RestrictedQuerySet
from nautobot.utilities.tables import BaseTable

from dolt.diff.factory import DiffModelFactory, DiffViewTableFactory
from dolt.diff.model_view_map import content_type_has_diff_view_table
from dolt.context_managers import query_at_commit


def diffable_content_types():

    return ContentType.objects.filter(
        app_label__in=(
            "dcim",
            # "circuits",
            "ipam",
            # "tenancy",
            # "virtualization",
        )
    )


def two_dot_diffs(from_commit=None, to_commit=None):
    if not (from_commit and to_commit):
        raise ValueError("must specify both a to_commit and from_commit")

    diff_results = []
    for content_type in diffable_content_types():
        if not content_type_has_diff_view_table(content_type):
            # todo(andy): fallback to generic diff view
            continue

        factory = DiffModelFactory(content_type)
        diffs = factory.get_model().objects.filter(
            from_commit=from_commit, to_commit=to_commit
        )
        to_queryset = list(
            content_type.model_class()
            .objects.filter(pk__in=diffs.values_list("to_id", flat=True))
            .annotate(
                diff_type=Subquery(
                    diffs.filter(to_id=OuterRef("id")).values("diff_type"),
                    output_field=models.CharField(),
                ),
                diff_root=Value("to", output_field=models.CharField()),
            )
        )
        with query_at_commit(from_commit):
            # must materialize list inside `query_at_commit()` content manager
            from_queryset = list(
                content_type.model_class()
                .objects.filter(pk__in=diffs.values_list("from_id", flat=True))
                .annotate(
                    diff_type=Subquery(
                        diffs.filter(from_id=OuterRef("id")).values("diff_type"),
                        output_field=models.CharField(),
                    ),
                    diff_root=Value("from", output_field=models.CharField()),
                )
            )

        diff_rows = sorted(to_queryset + from_queryset, key=lambda d: d.pk)
        if not len(diff_rows):
            continue

        diff_view_table = DiffViewTableFactory(content_type).get_table_model()
        diff_results.append(
            {
                "name": f"{factory.source_model_verbose_name} Diffs",
                "table": diff_view_table(diff_rows),
                "added": diffs.filter(diff_type="added").count(),
                "modified": diffs.filter(diff_type="modified").count(),
                "removed": diffs.filter(diff_type="removed").count(),
            }
        )
    return diff_results