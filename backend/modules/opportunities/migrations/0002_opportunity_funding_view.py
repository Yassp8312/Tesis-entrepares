from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("opportunities", "0001_opportunities_and_funding")]

    operations = [
        migrations.RunSQL(
            sql="""CREATE VIEW model_opportunity_funding AS
SELECT o.id AS opportunity_id, (f.opportunity_id IS NOT NULL) AS is_funded
FROM opportunities_opportunity o LEFT JOIN opportunities_funding f ON f.opportunity_id = o.id;""",
            reverse_sql="DROP VIEW model_opportunity_funding",
        ),
    ]
