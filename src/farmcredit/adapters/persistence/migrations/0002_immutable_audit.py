# SPDX-License-Identifier: AGPL-3.0-only
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("persistence", "0001_initial")]
    operations = [
        migrations.RunSQL(
            sql="""
        CREATE FUNCTION farmcredit_immutable_audit() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Saved assessments and reviews are immutable'
                USING ERRCODE = '23000';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER immutable_assessment BEFORE UPDATE OR DELETE ON persistence_assessment
            FOR EACH STATEMENT EXECUTE FUNCTION farmcredit_immutable_audit();
        CREATE TRIGGER immutable_review BEFORE UPDATE OR DELETE ON persistence_review
            FOR EACH STATEMENT EXECUTE FUNCTION farmcredit_immutable_audit();
        """,
            reverse_sql="""
        DROP TRIGGER immutable_assessment ON persistence_assessment;
        DROP TRIGGER immutable_review ON persistence_review;
        DROP FUNCTION farmcredit_immutable_audit();
        """,
        )
    ]
