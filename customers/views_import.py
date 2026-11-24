"""Admin pages to add many customers from an Excel file.

Flow: upload (POST) -> check page (GET, saves nothing) -> confirm (POST, saves
all rows or none) -> result page. The rules are the terminal command's rules
(`customers/importing.py`). Every view is admin only.
"""

from io import BytesIO
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from accounts.permissions import admin_required
from audit.services import get_client_ip
from customers import import_uploads
from customers.forms import ExcelUploadForm
from customers.importing import ImportFileError, ImportResult, import_customers

RESULT_KEY = "excel_import_result"
MAX_ERRORS_SHOWN = 50
EXPIRED = "ไฟล์ที่อัปโหลดหมดอายุแล้ว (เก็บไว้ 30 นาที) กรุณาอัปโหลดใหม่"


@admin_required
@require_http_methods(["GET", "POST"])
def customer_import(request: HttpRequest) -> HttpResponse:
    """Choose a file. Uploading only stores it; the check page reads it."""
    form = ExcelUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        import_uploads.save_upload(request, form.cleaned_data["file"])
        return redirect("customer_import_check")
    return render(request, "customers/import.html", {"form": form})


@admin_required
@require_GET
def customer_import_check(request: HttpRequest) -> HttpResponse:
    """What would happen, row by row. Saves nothing."""
    upload = import_uploads.current_upload(request)
    if upload is None:
        messages.info(request, EXPIRED)
        return redirect("customer_import")
    path, file_name = upload
    sheet = request.GET.get("sheet") or None
    context: dict = {"file_name": file_name, "sheet": sheet}
    try:
        result = import_customers(path, dry_run=True, sheet=sheet)
    except ImportFileError as error:
        context.update(file_error=error.thai, sheet_names=error.sheet_names)
        return render(request, "customers/import_check.html", context)
    context.update(_result_context(result), sheet=result.sheet_name)
    return render(request, "customers/import_check.html", context)


@admin_required
@require_POST
def customer_import_confirm(request: HttpRequest) -> HttpResponse:
    """Save every row, or none if any row is invalid."""
    upload = import_uploads.current_upload(request)
    if upload is None:
        messages.info(request, EXPIRED)
        return redirect("customer_import")
    path, file_name = upload
    sheet = request.POST.get("sheet") or None
    check_url = reverse("customer_import_check")
    try:
        result = import_customers(
            path,
            dry_run=False,
            sheet=sheet,
            user=request.user,
            ip_address=get_client_ip(request),
        )
    except ImportFileError as error:
        messages.error(request, error.thai)
        return redirect(check_url)
    if not result.ok:
        # Only if the check page was skipped: show the problems there.
        query = f"?{urlencode({'sheet': sheet})}" if sheet else ""
        return redirect(check_url + query)
    import_uploads.discard_upload(request)
    # Counts and row numbers only: never names, phones or account numbers.
    request.session[RESULT_KEY] = {
        "file_name": file_name,
        "created": result.created,
        "skipped_duplicates": result.skipped_duplicates,
        "invalid_account_rows": result.invalid_account_rows,
        "numeric_account_rows": result.numeric_account_rows,
        "duplicate_phone_rows": result.duplicate_phone_rows,
    }
    return redirect("customer_import_done")


@admin_required
@require_GET
def customer_import_done(request: HttpRequest) -> HttpResponse:
    """The result, shown once (a refresh goes back to the customers page)."""
    result = request.session.pop(RESULT_KEY, None)
    if result is None:
        return redirect("customer_list")
    return render(request, "customers/import_done.html", result)


# The client's own column order; the referral column is optional.
TEMPLATE_HEADERS = ["ทะเบียนรถ", "ชื่อ", "หมายเลขบัญชี", "ธนาคาร", "เบอร์โทร", "ผู้แนะนำ"]
TEXT_COLUMNS = ("C", "E")  # account number and phone keep their leading 0
TEMPLATE_ROWS = 1000


@admin_required
@require_GET
def customer_import_template(request: HttpRequest) -> HttpResponse:
    """An empty Excel file with the right headers. Holds no customer data."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ลูกค้า"
    sheet.append(TEMPLATE_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column in TEXT_COLUMNS:
        for row in range(2, TEMPLATE_ROWS + 2):
            sheet[f"{column}{row}"].number_format = "@"  # Excel "Text"
    for column, width in zip("ABCDEF", (16, 28, 20, 18, 16, 18), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="customers-template.xlsx"'
    return response


def _result_context(result: ImportResult) -> dict:
    return {
        "result": result,
        "sheet_names": result.sheet_names,
        "errors_shown": result.errors[:MAX_ERRORS_SHOWN],
        "errors_hidden": max(len(result.errors) - MAX_ERRORS_SHOWN, 0),
    }
