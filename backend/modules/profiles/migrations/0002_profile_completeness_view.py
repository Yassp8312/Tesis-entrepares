from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("profiles", "0001_profiles_and_education")]

    operations = [
        migrations.RunSQL(
            sql="""CREATE VIEW model_profile_completeness AS
SELECT p.id AS profile_id, p.account_id,
       EXISTS (SELECT 1 FROM profiles_education e WHERE e.profile_id = p.id AND e.ended_at IS NULL)
       AND EXISTS (SELECT 1 FROM profiles_contact c WHERE c.profile_id = p.id AND c.is_visible) AS is_complete
FROM profiles_profile p;""",
            reverse_sql="DROP VIEW model_profile_completeness",
        ),
    ]
