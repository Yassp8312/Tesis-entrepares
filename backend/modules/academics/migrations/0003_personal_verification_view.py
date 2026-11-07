from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0002_personal_verifications_and_researcher_awards")]

    operations = [
        migrations.RunSQL(
            sql="""CREATE VIEW model_personal_verification AS
SELECT a.id AS account_id,
       EXISTS (SELECT 1 FROM academics_personal_verification v WHERE v.account_id = a.id AND v.status = 'approved') AS is_verified
FROM identity_account a;""",
            reverse_sql="DROP VIEW model_personal_verification",
        ),
    ]
