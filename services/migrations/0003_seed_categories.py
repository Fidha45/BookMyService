from django.db import migrations


STARTER_CATEGORIES = [
    ("Home Cleaning", "home-cleaning"),
    ("Plumbing", "plumbing"),
    ("Electrical", "electrical"),
    ("Appliance Repair", "appliance-repair"),
    ("Beauty & Wellness", "beauty-wellness"),
    ("Painting", "painting"),
    ("Moving & Packing", "moving-packing"),
    ("Gardening", "gardening"),
]


def add_starter_categories(apps, schema_editor):
    Category = apps.get_model("services", "Category")
    database = schema_editor.connection.alias
    for name, slug in STARTER_CATEGORIES:
        Category.objects.using(database).get_or_create(slug=slug, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("services", "0002_favourite")]

    operations = [migrations.RunPython(add_starter_categories, migrations.RunPython.noop)]
