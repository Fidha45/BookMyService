from django.db import migrations


ASSESSMENT_CATEGORIES = [
    ("Laptop & Computer Repair", "laptop-computer-repair"),
    ("AC Service", "ac-service"),
    ("Car Service", "car-service"),
    ("Photography", "photography"),
    ("Website Development", "website-development"),
]


def add_assessment_categories(apps, schema_editor):
    Category = apps.get_model("services", "Category")
    database = schema_editor.connection.alias
    for name, slug in ASSESSMENT_CATEGORIES:
        Category.objects.using(database).get_or_create(slug=slug, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("services", "0003_seed_categories")]

    operations = [migrations.RunPython(add_assessment_categories, migrations.RunPython.noop)]
