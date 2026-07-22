from django.db import migrations, models
import django.core.validators
import budgets.storage
import django.db.models.deletion


JURISDICTIONS = [
    ("skagit-county", "Skagit County", "0158", "county", "https://www.skagitcounty.net/Departments/BudgetFinance/main.htm"),
    ("anacortes", "City of Anacortes", "0628", "city", "https://www.anacorteswa.gov/157/Finance"),
    ("burlington", "City of Burlington", "0633", "city", "https://burlingtonwa.gov/"),
    ("concrete", "Town of Concrete", "0636", "town", "https://www.townofconcrete.com/"),
    ("hamilton", "Town of Hamilton", "0638", "town", "https://townofhamiltonwa.com/"),
    ("la-conner", "Town of La Conner", "0640", "town", "https://www.townoflaconner.org/"),
    ("lyman", "Town of Lyman", "0642", "town", "https://townoflyman.com/"),
    ("mount-vernon", "City of Mount Vernon", "0644", "city", "https://mountvernonwa.gov/"),
    ("sedro-woolley", "City of Sedro-Woolley", "0647", "city", "https://www.sedro-woolley.gov/"),
]


def seed_jurisdictions(apps, schema_editor):
    Jurisdiction = apps.get_model("budgets", "BudgetJurisdiction")
    for slug, name, mcag, kind, official_url in JURISDICTIONS:
        Jurisdiction.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "mcag": mcag, "kind": kind, "official_url": official_url, "active": True},
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="BudgetJurisdiction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=200)),
                ("mcag", models.CharField(blank=True, db_index=True, max_length=12)),
                ("kind", models.CharField(blank=True, max_length=40)),
                ("official_url", models.URLField(blank=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="BudgetDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fiscal_year", models.PositiveSmallIntegerField(db_index=True)),
                ("title", models.CharField(max_length=300)),
                ("status", models.CharField(choices=[("proposed", "Proposed"), ("preliminary", "Preliminary"), ("adopted", "Adopted"), ("amended", "Amended")], db_index=True, max_length=20)),
                ("version_date", models.DateField(blank=True, null=True)),
                ("adopted_on", models.DateField(blank=True, null=True)),
                ("source_url", models.URLField(max_length=1000)),
                ("local_file", models.FileField(blank=True, storage=budgets.storage.budget_pdf_storage, upload_to=budgets.storage.budget_pdf_upload_to)),
                ("content_sha256", models.CharField(blank=True, db_index=True, max_length=64)),
                ("page_count", models.PositiveIntegerField(default=0)),
                ("extracted_summary", models.JSONField(blank=True, default=dict)),
                ("published", models.BooleanField(db_index=True, default=False)),
                ("is_current", models.BooleanField(db_index=True, default=False)),
                ("retrieved_at", models.DateTimeField(blank=True, null=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("jurisdiction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budget_documents", to="budgets.budgetjurisdiction")),
            ],
            options={"ordering": ["-fiscal_year", "-version_date", "-id"]},
        ),
        migrations.CreateModel(
            name="BudgetDocumentPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("text", models.TextField(blank=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pages", to="budgets.budgetdocument")),
            ],
            options={"ordering": ["page_number"]},
        ),
        migrations.CreateModel(
            name="BudgetLineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField(blank=True, null=True)),
                ("fiscal_year", models.PositiveSmallIntegerField(db_index=True)),
                ("side", models.CharField(choices=[("revenue", "Revenue"), ("expenditure", "Expenditure"), ("fund_balance", "Fund balance"), ("other", "Other")], db_index=True, max_length=20)),
                ("amount_kind", models.CharField(choices=[("requested", "Requested"), ("recommended", "Recommended"), ("adopted", "Adopted"), ("amended", "Amended"), ("actual", "Actual"), ("unknown", "Unknown")], default="unknown", max_length=20)),
                ("fund_code", models.CharField(blank=True, max_length=40)),
                ("fund_name", models.CharField(blank=True, max_length=240)),
                ("department_code", models.CharField(blank=True, max_length=40)),
                ("department_name", models.CharField(blank=True, max_length=240)),
                ("account_code", models.CharField(blank=True, max_length=80)),
                ("account_name", models.CharField(blank=True, max_length=300)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=22)),
                ("raw_label", models.TextField(blank=True)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="line_items", to="budgets.budgetdocument")),
            ],
            options={"ordering": ["side", "fund_code", "department_code", "account_code", "id"]},
        ),
        migrations.CreateModel(
            name="BudgetImportRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="running", max_length=20)),
                ("pages_extracted", models.PositiveIntegerField(default=0)),
                ("candidate_line_items", models.PositiveIntegerField(default=0)),
                ("warnings", models.JSONField(blank=True, default=list)),
                ("error", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="import_runs", to="budgets.budgetdocument")),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddConstraint(model_name="budgetdocument", constraint=models.UniqueConstraint(fields=("jurisdiction", "source_url", "content_sha256"), name="budget_document_source_hash_unique")),
        migrations.AddIndex(model_name="budgetdocument", index=models.Index(fields=["jurisdiction", "fiscal_year", "published"], name="budgets_bud_jurisdi_8351be_idx")),
        migrations.AddIndex(model_name="budgetdocument", index=models.Index(fields=["jurisdiction", "is_current"], name="budgets_bud_jurisdi_63b3db_idx")),
        migrations.AddConstraint(model_name="budgetdocumentpage", constraint=models.UniqueConstraint(fields=("document", "page_number"), name="budget_document_page_unique")),
        migrations.AddIndex(model_name="budgetlineitem", index=models.Index(fields=["document", "side"], name="budgets_bud_documen_10b4fd_idx")),
        migrations.AddIndex(model_name="budgetlineitem", index=models.Index(fields=["fiscal_year", "side"], name="budgets_bud_fiscal__66d1fe_idx")),
        migrations.AddIndex(model_name="budgetlineitem", index=models.Index(fields=["fund_code"], name="budgets_bud_fund_co_44f612_idx")),
        migrations.RunPython(seed_jurisdictions, migrations.RunPython.noop),
    ]
