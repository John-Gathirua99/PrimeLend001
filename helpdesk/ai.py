




def generate_ai_reply(message):
    msg = message.lower()

    # OTP issues
    if any(word in msg for word in ['otp', 'code', 'verification']):
        return (
            "If you didn’t receive an OTP:\n"
            "• Ensure your phone number is correct\n"
            "• Check network availability\n"
            "• Try resending after 1 minute\n\n"
            "If the issue persists, admin support will assist you."
        )

    # Loan status
    if any(word in msg for word in ['loan status', 'approved', 'rejected', 'pending']):
        return (
            "You can view your loan status in the dashboard.\n"
            "• Pending: Under review\n"
            "• Approved: Awaiting disbursement\n"
            "• Rejected: Reason provided by admin\n\n"
            "Disbursement usually takes less than 24 hours."
        )

    # Loan rejection appeal
    if any(word in msg for word in ['appeal', 'reconsider', 'rejected loan']):
        return (
            "Loan rejections are based on income, credit history, and risk assessment.\n"
            "You may improve approval chances by:\n"
            "• Applying for a smaller amount\n"
            "• Increasing repayment period\n"
            "• Ensuring accurate details\n\n"
            "An admin will review your appeal."
        )

    # Repayment
    if any(word in msg for word in ['repay', 'payment', 'mpesa']):
        return (
            "Loan repayments are made via M-Pesa.\n"
            "Payment details are available in your dashboard.\n"
            "Ensure you pay before the due date to avoid penalties."
        )

    # Fraud flags
    if any(word in msg for word in ['fraud', 'flagged', 'blocked']):
        return (
            "Some applications are flagged automatically for security reasons.\n"
            "This does not mean rejection.\n"
            "An admin will manually review your application shortly."
        )

    # Login / account
    if any(word in msg for word in ['login', 'account', 'password']):
        return (
            "If you cannot log in:\n"
            "• Ensure credentials are correct\n"
            "• Verify your phone number\n"
            "• Reset password if needed\n\n"
            "Admin support can help if the issue continues."
        )

    # Default fallback
    return (
        "Thank you for contacting support.\n"
        "Our AI has received your query and an admin will respond shortly if needed."
    )



ADMIN_TRIGGER_PHRASES = [
    'connect me to admin',
    'talk to admin',
    'human support',
    'agent',
    'real person',
    'customer care',
    'person',
    'human server',

]

def wants_admin(message):
    msg = message.lower()
    return any(phrase in msg for phrase in ADMIN_TRIGGER_PHRASES)
