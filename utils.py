import qrcode
from io import BytesIO
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def generate_upi_qr(upi_id: str, amount: float, name: str = "Merchant") -> BytesIO:
    """Generate UPI QR code"""
    try:
        # UPI payment string format
        upi_string = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_string)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        bio = BytesIO()
        bio.name = 'qr.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        
        return bio
    except Exception as e:
        logger.error(f"Error generating QR code: {e}")
        return None


def format_order_details(order: dict) -> str:
    """Format order details for display"""
    status_emoji = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌',
        'delivered': '📦',
        'cancelled': '🚫'
    }
    
    emoji = status_emoji.get(order['status'], '❓')
    
    text = f"""
📋 **Order Details** 
Order ID: `{order['order_number']}`
Coupon: **{order['coupon_name']}** Quantity: {order['quantity']}
Total Price: ₹{order['total_price']:.2f}
Status: {emoji} {order['status'].upper()}
Date: {order['created_at']}
"""
    
    if 'utr' in order:
        text += f"\nUTR: `{order['utr']}`"
    
    return text


def format_order_for_admin(order: dict) -> str:
    """Format order details for admin"""
    text = f"""
🆕 **New Order #{order['id']}** 
Order Number: `{order['order_number']}`
User: @{order.get('username', 'N/A')} (ID: {order['telegram_id']})
Coupon: **{order['coupon_name']}** Quantity: {order['quantity']}
Total: ₹{order['total_price']:.2f}
UTR: `{order['utr']}`
Status: {order['status'].upper()}
Created: {order['created_at']}
"""
    return text


def format_coupon_list(coupons: list) -> str:
    """Format coupon list for display"""
    if not coupons:
        return "❌ No coupons available at the moment."
    
    text = "🛍️ **Available Coupons:** \n\n"
    for coupon in coupons:
        stock_status = f"✅ {coupon['stock']} in stock" if coupon['stock'] > 0 else "❌ Out of stock"
        text += f" **{coupon['name']}** \n"
        text += f"Price: ₹{coupon['price']}\n"
        text += f"Stock: {stock_status}\n\n"
    
    return text


def validate_utr(utr: str) -> bool:
    """Basic UTR validation (12 digits)"""
    return utr.isdigit() and len(utr) == 12


def format_codes_message(codes: list) -> str:
    """Format coupon codes for delivery"""
    text = "🎉 **Your Coupon Codes:** \n\n"
    for idx, code in enumerate(codes, 1):
        text += f"{idx}. `{code}`\n"
    text += "\n✅ Thank you for your purchase!"
    return text