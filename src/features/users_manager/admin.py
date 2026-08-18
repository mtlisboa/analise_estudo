from django.contrib import admin

from .models import Classroom, ClassroomMembership, EducationalRelationship, SelfAssessment

admin.site.register(EducationalRelationship)
admin.site.register(Classroom)
admin.site.register(ClassroomMembership)
admin.site.register(SelfAssessment)
