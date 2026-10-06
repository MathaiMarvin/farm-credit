# SPDX-License-Identifier: AGPL-3.0-only
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("persistence", "0003_draft")]
    operations = [
        migrations.RunSQL(
            sql="""
            CREATE FUNCTION farmcredit_immutable_draft() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Saved drafts are immutable' USING ERRCODE = '23000';
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER immutable_draft BEFORE UPDATE OR DELETE ON persistence_draft
                FOR EACH STATEMENT EXECUTE FUNCTION farmcredit_immutable_draft();
            """,
            reverse_sql="""
            DROP TRIGGER immutable_draft ON persistence_draft;
            DROP FUNCTION farmcredit_immutable_draft();
            """,
        ),
    ]
