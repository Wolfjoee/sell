from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import *
from utils import *
from config import UPI_ID
import logging

logger = logging.getLogger(__name__)
user_router = Router()


class BuyState(StatesGroup):
    waiting_for_utr = State()


@user_router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    # Register user
    await db.add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    welcome_text = f"""
👋 Welcome **{message.from_user.first_name}** !

I'm your Digital Coupon Assistant. Here you can:

🛍️ Browse available coupons
💳 Purchase coupons instantly
📋 Track your orders
🎁 Receive codes automatically

Select an option below to get started!
"""
    
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())


@user_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    await state.clear()
    
    welcome_text = """
🏠 **Main Menu** 
What would you like to do?
"""
    
    await callback.message.edit_text(welcome_text, reply_markup=main_menu_keyboard())
    await callback.answer()


@user_router.callback_query(F.data == "browse_coupons")
async def browse_coupons(callback: CallbackQuery):
    """Show available coupons"""
    coupons = await db.get_all_coupons()
    
    if not coupons:
        await callback.answer("❌ No coupons available at the moment.", show_alert=True)
        return
    
    text = "🛍️ **Available Coupons** \n\n"
    text += "Select a coupon to view details and purchase:\n"
    
    await callback.message.edit_text(text, reply_markup=coupons_list_keyboard(coupons))
    await callback.answer()


@user_router.callback_query(F.data.startswith("select_coupon_"))
async def select_coupon(callback: CallbackQuery, state: FSMContext):
    """Show coupon details and quantity selection"""
        coupon_id = int(callback.data.split("_")[2])
    
    coupon = await db.get_coupon_by_id(coupon_id)
    if not coupon:
        await callback.answer("❌ Coupon not found!", show_alert=True)
        return
    
    if coupon['stock'] == 0:
        await callback.answer("❌ This coupon is out of stock!", show_alert=True)
        return
    
    # Store coupon info in state
    await state.update_data(coupon_id=coupon_id)
    
    text = f"""
📦 **{coupon['name']}** 
💰 Price: ₹{coupon['price']} per code
📊 Available Stock: {coupon['stock']} codes
 **Select Quantity:** (Maximum 10 per order)
"""
    
    max_qty = min(coupon['stock'], 10)
    await callback.message.edit_text(text, reply_markup=quantity_keyboard(coupon_id, max_qty))
    await callback.answer()


@user_router.callback_query(F.data.startswith("qty_"))
async def select_quantity(callback: CallbackQuery, state: FSMContext):
    """Process quantity selection and show payment details"""
    parts = callback.data.split("_")
    coupon_id = int(parts[1])
    quantity = int(parts[2])
    
    coupon = await db.get_coupon_by_id(coupon_id)
    if not coupon:
        await callback.answer("❌ Coupon not found!", show_alert=True)
        return
    
    if coupon['stock'] < quantity:
        await callback.answer(f"❌ Only {coupon['stock']} codes available!", show_alert=True)
        return
    
    total_price = coupon['price'] * quantity
    
    # Generate unique order number (temporary, will be created in DB after UTR)
    temp_order_number = f"TEMP{callback.from_user.id}{int(datetime.now().timestamp())}"
    
    # Store order details in state
    await state.update_data(
        coupon_id=coupon_id,
        coupon_name=coupon['name'],
        quantity=quantity,
        total_price=total_price,
        temp_order_number=temp_order_number
    )
    
    # Generate UPI QR code
    qr_image = generate_upi_qr(UPI_ID, total_price, "Coupon Store")
    
    payment_text = f"""
💳 **Payment Details** 
📦 Coupon: **{coupon['name']}** 🔢 Quantity: {quantity}
💰 Total Amount: **₹{total_price:.2f}**  **UPI ID:** `{UPI_ID}`

📱 **Payment Instructions:** 1. Scan the QR code below OR use the UPI ID
2. Pay exactly ₹{total_price:.2f}
3. After payment, click "I've Paid" button
4. Enter your 12-digit UTR number
5. Wait for admin approval
6. Codes will be delivered automatically!

⚠️ **Important:** 
- Payment is verified manually by admin
- Do not make duplicate payments
- Keep your UTR number ready
"""
    
    await callback.message.delete()
    
    if qr_image:
        await callback.message.answer_photo(
            photo=qr_image,
            caption=payment_text,
            reply_markup=payment_confirmation_keyboard(temp_order_number)
        )
    else:
        await callback.message.answer(
            payment_text,
            reply_markup=payment_confirmation_keyboard(temp_order_number)
        )
    
    await callback.answer()


@user_router.callback_query(F.data.startswith("submit_utr_"))
async def submit_utr_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt user to enter UTR"""
    await state.set_state(BuyState.waiting_for_utr)
    
    text = """
📝 **Enter UTR Number** 
Please send your 12-digit UTR/Transaction ID:

Example: `123456789012`

This is the unique transaction reference number you received after payment.
"""
    
    await callback.message.answer(text, reply_markup=cancel_keyboard())
    await callback.answer()


@user_router.callback_query(F.data == "cancel_operation")
async def cancel_operation(callback: CallbackQuery, state: FSMContext):
    """Cancel current operation"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "❌ Operation cancelled.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@user_router.message(BuyState.waiting_for_utr)
async def process_utr(message: Message, state: FSMContext):
    """Process UTR submission and create order"""
    utr = message.text.strip()
    
    # Validate UTR format
    if not validate_utr(utr):
        await message.answer(
            "❌ Invalid UTR format!\n\n"
            "UTR must be exactly 12 digits.\n"
            "Please try again:",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Check for duplicate UTR
    if await db.check_duplicate_utr(utr):
        await message.answer(
            "⚠️ This UTR has already been submitted!\n\n"
            "If you believe this is an error, please contact support.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    # Get order details from state
    data = await state.get_data()
    coupon_id = data.get('coupon_id')
    quantity = data.get('quantity')
    total_price = data.get('total_price')
    coupon_name = data.get('coupon_name')
    
    # Verify stock availability again
    coupon = await db.get_coupon_by_id(coupon_id)
    if not coupon or coupon['stock'] < quantity:
        await message.answer(
            "❌ Sorry, this coupon is no longer available in the requested quantity.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    # Create order in database
    try:
        # Get user internal ID
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute(
                'SELECT id FROM users WHERE telegram_id = ?',
                (message.from_user.id,)
            ) as cursor:
                user_row = await cursor.fetchone()
                if not user_row:
                    await message.answer("❌ User not found. Please /start again.")
                    return
                user_id = user_row[0]
        
        order_number = await db.create_order(
            user_id=user_id,
            coupon_id=coupon_id,
            quantity=quantity,
            total_price=total_price,
            utr=utr
        )
        
        # Confirmation message to user
        confirmation_text = f"""
✅ **Order Submitted Successfully!** 
📋 Order Number: `{order_number}`
📦 Coupon: **{coupon_name}** 🔢 Quantity: {quantity}
💰 Total: ₹{total_price:.2f}
🔑 UTR: `{utr}`

⏳ Your order is now **pending approval** .

Once our admin verifies your payment, you will automatically receive your coupon codes.

You can check your order status anytime using the "My Orders" button.
"""
        
        await message.answer(confirmation_text, reply_markup=main_menu_keyboard())
        
        # Notify admins
        from config import ADMIN_IDS
        order = await db.get_order_by_number(order_number)
        if order:
            admin_notification = format_order_for_admin(order)
            admin_notification += f"\n\nUse /approve {order['id']} to approve this order"
            
            for admin_id in ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        admin_notification,
                        reply_markup=order_action_keyboard(order['id'])
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        await message.answer(
            "❌ An error occurred while creating your order. Please try again.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()


@user_router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    """Cancel order before UTR submission"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "❌ Order cancelled successfully.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@user_router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: CallbackQuery):
    """Show user's order history"""
    orders = await db.get_user_orders(callback.from_user.id)
    
    if not orders:
        await callback.answer("📋 You haven't placed any orders yet.", show_alert=True)
        return
    
    text = "📋 **Your Orders:** \n\n"
    
    for order in orders[:10]:  # Show last 10 orders
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌',
            'delivered': '📦',
            'cancelled': '🚫'
        }
        emoji = status_emoji.get(order['status'], '❓')
        
        text += f"{emoji} `{order['order_number']}`\n"
        text += f"   {order['coupon_name']} × {order['quantity']}\n"
        text += f"   ₹{order['total_price']:.2f} - {order['status'].upper()}\n\n"
    
    if len(orders) > 10:
        text += f"\n_Showing 10 of {len(orders)} orders_"
    
    await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@user_router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Show help information"""
    help_text = """
ℹ️ **Help & Instructions**  **How to Buy:** 1. Click "Browse Coupons"
2. Select a coupon
3. Choose quantity
4. Pay via UPI
5. Submit UTR number
6. Wait for approval
7. Receive codes automatically!
 **Order Status:** - ⏳ Pending: Waiting for admin verification
- ✅ Approved: Payment verified
- 📦 Delivered: Codes sent to you
- ❌ Rejected: Payment issue
 **Need Support?** Contact admin if you face any issues.
 **Payment:** - Use UPI only
- Pay exact amount
- Keep UTR ready
- No refunds for wrong UTR

Happy Shopping! 🛍️
"""
    
    await callback.message.edit_text(help_text, reply_markup=back_to_menu_keyboard())
    await callback.answer()