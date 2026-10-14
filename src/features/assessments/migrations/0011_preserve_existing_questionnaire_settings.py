from django.db import migrations


def preserve(apps, schema_editor):
    Assessment = apps.get_model('assessments', 'Assessment')
    Publication = apps.get_model('institution_coursework', 'Publication')
    ExamRun = apps.get_model('paper_exams', 'ExamRun')
    for assessment in Assessment.objects.iterator():
        pubs = Publication.objects.filter(assessment_id=assessment.pk).order_by('-is_published', '-pk')
        publication = pubs.first()
        assessment.is_visible = pubs.filter(is_published=True).exists()
        assessment.due_at = publication.due_at if publication else None
        if not publication and ExamRun.objects.filter(assessment_id=assessment.pk).exists():
            assessment.delivery_mode = 'printed'
        assessment.save(update_fields=['is_visible', 'due_at', 'delivery_mode'])


class Migration(migrations.Migration):
    dependencies = [('assessments','0010_assessment_delivery_mode_assessment_due_at_and_more'),
        ('institution_coursework','0003_publication_grading_snapshot_submission_and_more'),
        ('paper_exams','0004_examrun_context_resultreview_open_scores_and_more')]
    operations = [migrations.RunPython(preserve, migrations.RunPython.noop)]
