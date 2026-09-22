from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import InstitutionDataExport, Organization, School
from .services import create_institution_export


@receiver(pre_delete, sender=Organization, dispatch_uid="export_organization_before_delete")
def export_organization_before_delete(sender, instance, using, **kwargs):
    create_institution_export(
        instance,
        trigger=InstitutionDataExport.Trigger.ORGANIZATION_DELETE,
    )


@receiver(pre_delete, sender=School, dispatch_uid="export_school_before_delete")
def export_school_before_delete(sender, instance, using, **kwargs):
    create_institution_export(
        instance.organization,
        trigger=InstitutionDataExport.Trigger.SCHOOL_DELETE,
    )
