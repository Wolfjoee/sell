from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard for users"""
    buttons = [
        [InlineKeyboardButton(text="🛍️ Browse Coupons", callback_data="browse_coupons")],
        [InlineKeyboardButton(text="📋 My Orders", callback_data="my_orders")],
        [InlineKeyboardButton(text="ℹ️ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Admin menu keyboard"""
    buttons = [
        [InlineKeyboardButton(text="➕ Add Coupon", callback_data="admin_add_coupon")],
        [InlineKeyboardButton(text="📦 Manage Stock", callback_data="admin_manage_stock")],
        [InlineKeyboardButton(text="📋 View Orders", callback_data="admin_view_orders")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def coupons_list_keyboard(coupons: List[Dict]) -> InlineKeyboardMarkup:
    """Display coupons as inline buttons"""
    buttons = []
    for coupon in coupons:
        stock_text = f"({coupon['stock']} left)" if coupon['stock'] > 0 else "(Out of stock)"
        button_text = f"{coupon['name']} - ₹{coupon['price']} {stock_text}"
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"select_coupon_{coupon['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quantity_keyboard(coupon_id: int, max_quantity: int = 10) -> InlineKeyboardMarkup:
    """Quantity selection keyboard"""
    buttons = []
    # Create rows of quantity buttons
    row = []
    for i in range(1, min(max_quantity + 1, 11)):
        row.append(InlineKeyboardButton(
            text=str(i),
            callback_data=f"qty_{coupon_id}_{i}"
        ))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="browse_coupons")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_confirmation_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Payment confirmation keyboard"""
    buttons = [
        [InlineKeyboardButton(text="✅ I've Paid - Submit UTR", callback_data=f"submit_utr_{order_number}")],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"cancel_order_{order_number}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_status_keyboard() -> InlineKeyboardMarkup:
    """Order status filter keyboard for admin"""
    buttons = [
        [
            InlineKeyboardButton(text="⏳ Pending", callback_data="orders_pending"),
            InlineKeyboardButton(text="✅ Approved", callback_data="orders_approved")
        ],
        [
            InlineKeyboardButton(text="❌ Rejected", callback_data="orders_rejected"),
            InlineKeyboardButton(text="📦 All", callback_data="orders_all")
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_action_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Order action keyboard for admin"""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_view_orders")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Simple back to menu button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
    ])


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    """Simple back to admin menu button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin Menu", callback_data="admin_menu")]
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Cancel current operation"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_operation")]
    ])