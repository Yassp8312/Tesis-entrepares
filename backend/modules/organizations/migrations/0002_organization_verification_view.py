from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_organizations_and_representation")]

    operations = [
        migrations.RunSQL(
            sql="""CREATE VIEW model_organization_verification AS
SELECT o.id AS organization_id,
       EXISTS (SELECT 1 FROM organizations_verification v WHERE v.organization_id = o.id AND v.status = 'approved') AS is_verified
FROM organizations_organization o;""",
            reverse_sql="DROP VIEW model_organization_verification",
        ),
    ]
