
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from django.http import HttpResponse
from datetime import date
from .models import RepaymentSchedule
from notification.utils import create_notification
from notification.email_util import send_loan_email

def generate_loan_statement(loan):

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="loan_{loan.id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        textColor=colors.white,
        fontSize=11,
        leading=14,
    )

    elements = []

    # Header
    header = Table(
        [["AI Loan System", "Official Loan Statement"]],
        colWidths=[250, 250],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.darkgreen),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 16),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 12),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 12))

    # Description
    desc = f"""
    This statement summarizes your loan with AI Loan System.
    Approved amount, repayments, and balance are shown below.
    """
    desc_table = Table([[Paragraph(desc, body_style)]], colWidths=[500])
    desc_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.green),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    elements.append(desc_table)
    elements.append(Spacer(1, 14))

    # Loan data
    data = [
        ["Customer", loan.full_name],
        ["Loan Amount", f"KES {loan.qualified_amount}"],
        ["Interest Rate", f"{loan.interest_rate}%"],
        ["Total Payable", f"KES {loan.amount_remaining + loan.qualified_amount}"],
        ["Amount Remaining", f"KES {loan.amount_remaining}"],
        ["Status", loan.status],
    ]

    table = Table(data, colWidths=[250, 250])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    # Footer
    footer = Table(
        [["AI Loan System • Nairobi, Kenya • support@ailoansystem.com"]],
        colWidths=[500],
    )
    footer.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.darkgreen),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    elements.append(footer)

    doc.build(elements)
    return response






def send_today_repayment_reminders():
    today = date.today()

    schedules = RepaymentSchedule.objects.select_related("loan__user").filter(
        due_date=today,
        paid=False
    )

    for s in schedules:
        user = s.loan.user

        create_notification(
            user,
            'Loan Scheduke',
            f"Reminder: Loan installment {s.installment_number} "
            f"of KES {s.amount} is due today."
        )


        send_loan_email(
            s.loan.user,
            "Loan Repayment Due Today",
            f"Your repayment of KES {s.installment_amount} is due today."
)

        