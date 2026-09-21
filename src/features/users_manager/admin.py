from django.contrib import admin

from .models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    ClassroomTest,
    EducationalRelationship,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)

admin.site.register(EducationalRelationship)
admin.site.register(Classroom)
admin.site.register(ClassroomGroup)
admin.site.register(ClassroomMembership)
admin.site.register(SelfAssessment)
admin.site.register(Organization)
admin.site.register(OrganizationMembership)
admin.site.register(ClassroomTest)
