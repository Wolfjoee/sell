from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import *
from utils import *
from config import ADMIN_IDS, UPI_ID, UPI_NAME, LOW_CODE_THRESHOLD
import logging
import aiosqlite
from datetime import datetime

logger = logging.getLogger(__name__)

# Create routers
user_router = Router()
admin_router = Router()
payment_router = Router()


# ============================================================================
# USER HANDLERS
# ============================================================================

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
    
    # Generate unique temporary order number
    temp_order_number = f"TEMP{callback.from_user.id}{int(datetime.now().timestamp())}"
    
    # Store order details in state
    await state.update_data(
        coupon_id=coupon_id,
        coupon_name=coupon['name'],
        quantity=quantity,
        total_price=total_price,
        temp_order_number=temp_order_number
    )
    
    # Generate UPI QR code dynamically
    qr_image = generate_upi_qr(UPI_ID, total_price, UPI_NAME)
    
    payment_text = f"""
💳 **Payment Details** 
📦 Coupon: **{coupon['name']}** 🔢 Quantity: {quantity}
💰 Total Amount: **₹{total_price:.2f}**  **Pay To:** UPI ID: `{UPI_ID}`
Name: {UPI_NAME}

📱 **Payment Instructions:** 1. Scan the QR code below OR copy UPI ID
2. Pay **exactly ₹{total_price:.2f}** 3. After successful payment, click "I've Paid" button
4. Enter your 12-digit UTR/Transaction ID
5. Wait for admin approval
6. Your codes will be delivered automatically!

⚠️ **Important:** • Payment is verified manually
• Keep your UTR number ready
• Do NOT make duplicate payments
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
            payment_text + "\n\n⚠️ QR generation failed. Use UPI ID.",
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
        order = await db.get_order_by_number(order_number)
        if order:
            admin_notification = format_order_for_admin(order)
            admin_notification += f"\n\nUse /approve {order['id']} to approve"
            
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
            "❌ An error occurred. Please try again.",
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
    
    for order in orders[:10]:
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
 **Order Status:** - ⏳ Pending: Waiting for verification
- ✅ Approved: Payment verified
- 📦 Delivered: Codes sent
- ❌ Rejected: Payment issue
 **Need Support?** Contact admin for assistance.

Happy Shopping! 🛍️
"""
    
    await callback.message.edit_text(help_text, reply_markup=back_to_menu_keyboard())
    await callback.answer()


# ============================================================================
# ADMIN HANDLERS
# ============================================================================

class AdminState(StatesGroup):
    adding_coupon_name = State()
    adding_coupon_price = State()
    adding_codes = State()
    broadcasting = State()


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS


@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    """Admin panel command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have admin access.")
        return
    
    text = """
👑 **Admin Panel** 
Welcome to the admin dashboard!
Select an option below:
"""
    
    await message.answer(text, reply_markup=admin_menu_keyboard())


@admin_router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Return to admin menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await state.clear()
    
    text = """
👑 **Admin Panel** 
Select an option:
"""
    
    await callback.message.edit_text(text, reply_markup=admin_menu_keyboard())
    await callback.answer()


@admin_router.message(Command("add"))
async def quick_add_coupon(message: Message):
    """Quick add coupon"""
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "❌ Usage: `/add <name> <price>`\n\n"
            "Example: `/add Netflix499 499`"
        )
        return
    
    coupon_name = args[1]
    try:
        price = float(args[2])
    except ValueError:
        await message.answer("❌ Invalid price!")
        return
    
    if price <= 0:
        await message.answer("❌ Price must be greater than 0!")
        return
    
    success = await db.add_coupon(coupon_name, price)
    
    if success:
        await message.answer(
            f"✅ **Coupon Created!** \n\n"
            f"Name: {coupon_name}\n"
            f"Price: ₹{price}\n\n"
            f"Now add codes using:\n"
            f"`/addcodes {coupon_name}`"
        )
    else:
        await message.answer(f"❌ Coupon '{coupon_name}' already exists!")


@admin_router.message(Command("addcodes"))
async def add_codes_command(message: Message, state: FSMContext):
    """Start adding coupon codes"""
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ Usage: `/addcodes <coupon_name>`\n\n"
            "Example: `/addcodes Amazon100`"
        )
        return
    
    coupon_name = args[1].strip()
    coupon = await db.get_coupon_by_name(coupon_name)
    
    if not coupon:
        await message.answer(f"❌ Coupon '{coupon_name}' not found!")
        return
    
    await state.update_data(coupon_id=coupon['id'], coupon_name=coupon_name)
    await state.set_state(AdminState.adding_codes)
    
    await message.answer(
        f"📦 **Adding Codes to: {coupon_name}** \n\n"
        f"Current Stock: {coupon['stock']} codes\n\n"
        f"Send coupon codes (one per line):\n\n"
        f"Example:\n"
        f"`CODE-ABC-123`\n"
        f"`CODE-DEF-456`\n\n"
        f"Send /done when finished",
        reply_markup=cancel_keyboard()
    )


@admin_router.message(AdminState.adding_codes, Command("done"))
async def finish_adding_codes(message: Message, state: FSMContext):
    """Finish adding codes"""
    await state.clear()
    await message.answer(
        "✅ Finished adding codes!",
        reply_markup=admin_menu_keyboard()
    )


@admin_router.message(AdminState.adding_codes)
async def process_codes(message: Message, state: FSMContext):
    """Process coupon codes bulk entry"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    coupon_id = data['coupon_id']
    coupon_name = data['coupon_name']
    
    # Split codes by newline
    codes = [code.strip() for code in message.text.split('\n') if code.strip()]
    
    if not codes:
        await message.answer("❌ No valid codes found!")
        return
    
    # Add codes to database
    added, duplicates = await db.add_coupon_codes(coupon_id, codes)
    
    total, available = await db.get_code_count(coupon_id)
    
    response = f"✅ **Codes Added!** \n\n"
    response += f"Coupon: {coupon_name}\n"
    response += f"✅ Added: {added} codes\n"
    
    if duplicates > 0:
        response += f"⚠️ Duplicates skipped: {duplicates}\n"
    
    response += f"\n📊 Total Stock: {available} codes available\n\n"
    response += f"Send more codes or /done to finish"
    
    await message.answer(response)


@admin_router.callback_query(F.data == "admin_manage_stock")
async def manage_stock(callback: CallbackQuery):
    """Show stock management"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    coupons = await db.get_all_coupons()
    
    if not coupons:
        await callback.message.edit_text(
            "❌ No coupons found!",
            reply_markup=back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "📦 **Stock Management** \n\n"
    
    for coupon in coupons:
        total, available = await db.get_code_count(coupon['id'])
        used = total - available
        
        status = "✅" if available > LOW_CODE_THRESHOLD else "⚠️"
        
        text += f"{status} **{coupon['name']}** \n"
        text += f"   Price: ₹{coupon['price']}\n"
        text += f"   Available: {available} codes\n"
        text += f"   Used: {used} codes\n"
        text += f"   Total: {total} codes\n\n"
    
    text += f"\n_Add codes: `/addcodes <coupon_name>`_"
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_view_orders")
async def view_orders_menu(callback: CallbackQuery):
    """Show orders filter menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📋 **Order Management** \n\nFilter orders by status:",
        reply_markup=order_status_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("orders_"))
async def view_orders_filtered(callback: CallbackQuery):
    """Show filtered orders"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    filter_type = callback.data.split("_")[1]
    
    if filter_type == "all":
        orders = await db.get_all_orders()
        title = "All Orders"
    else:
        orders = await db.get_all_orders(status=filter_type)
        title = f"{filter_type.capitalize()} Orders"
    
    if not orders:
        await callback.answer(f"No {filter_type} orders found.", show_alert=True)
        return
    
    text = f"📋 **{title}** \n\n"
    
    for order in orders[:15]:
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌',
            'delivered': '📦'
        }
        emoji = status_emoji.get(order['status'], '❓')
        
        text += f"{emoji} **Order #{order['id']}** \n"
        text += f"   User: @{order['username'] or 'N/A'}\n"
        text += f"   Coupon: {order['coupon_name']} × {order['quantity']}\n"
        text += f"   Total: ₹{order['total_price']:.2f}\n"
        text += f"   UTR: `{order['utr']}`\n\n"
    
    if len(orders) > 15:
        text += f"\n_Showing 15 of {len(orders)} orders_\n"
    
    text += f"\n💡 Use `/approve <order_id>` or `/reject <order_id>`"
    
    await callback.message.edit_text(text, reply_markup=order_status_keyboard())
    await callback.answer()


@admin_router.message(Command("approve"))
@admin_router.callback_query(F.data.startswith("approve_"))
async def approve_order(event, state: FSMContext):
    """Approve order and auto-deliver codes"""
    user_id = event.from_user.id if hasattr(event, 'from_user') else event.message.from_user.id
    
    if not is_admin(user_id):
        return
    
    # Get order ID
    if isinstance(event, Message):
        args = event.text.split()
        if len(args) < 2:
            await event.answer("❌ Usage: `/approve <order_id>`")
            return
        try:
            order_id = int(args[1])
        except ValueError:
            await event.answer("❌ Invalid order ID!")
            return
        message = event
    else:
        order_id = int(event.data.split("_")[1])
        message = event.message
    
    # Get order details
    order = await db.get_order(order_id)
    
    if not order:
        await message.answer("❌ Order not found!")
        return
    
    if order['status'] != 'pending':
        await message.answer(f"⚠️ Order is already {order['status']}!")
        return
    
    # Check available codes
    available_codes = await db.get_available_codes(order['coupon_id'], order['quantity'])
    
    if len(available_codes) < order['quantity']:
        await message.answer(
            f"❌ **Insufficient Coupon Codes!** \n\n"
            f"Required: {order['quantity']} codes\n"
            f"Available: {len(available_codes)} codes\n\n"
            f"Add more: `/addcodes {order['coupon_name']}`"
        )
        return
    
    try:
        # Fetch codes
        codes_to_deliver = available_codes[:order['quantity']]
        
        # Mark as used
        await db.mark_codes_as_used(
            order['coupon_id'],
            codes_to_deliver,
            order['user_id']
        )
        
        # Update order
        await db.update_order_status(order_id, 'delivered')
        
        # Send to user
        codes_message = format_codes_message(codes_to_deliver)
        order_info = f"📦 Order: `{order['order_number']}`\n"
        order_info += f"Coupon: **{order['coupon_name']}** \n\n"
        
        try:
            await message.bot.send_message(
                order['telegram_id'],
                order_info + codes_message
            )
            delivery_status = "✅ Codes delivered!"
        except Exception as e:
            logger.error(f"Failed to send codes: {e}")
            delivery_status = "⚠️ Failed to send codes!"
        
        # Confirm to admin
        confirmation = f"""
✅ **Order Approved & Delivered!** 
Order ID: #{order_id}
User: @{order['username']}
Coupon: {order['coupon_name']}
Quantity: {order['quantity']}

{delivery_status}
"""
        
        await message.answer(confirmation, reply_markup=admin_menu_keyboard())
        
        # Low stock check
        coupon = await db.get_coupon_by_id(order['coupon_id'])
        if coupon and coupon['stock'] <= LOW_CODE_THRESHOLD:
            await message.answer(
                f"⚠️ **Low Stock Alert!** \n\n"
                f"Coupon: {coupon['name']}\n"
                f"Remaining: {coupon['stock']} codes"
            )
        
    except Exception as e:
        logger.error(f"Error approving order: {e}")
        await message.answer(f"❌ Error: {str(e)}")


@admin_router.message(Command("reject"))
@admin_router.callback_query(F.data.startswith("reject_"))
async def reject_order(event, state: FSMContext):
    """Reject an order"""
    user_id = event.from_user.id if hasattr(event, 'from_user') else event.message.from_user.id
    
    if not is_admin(user_id):
        return
    
    # Get order ID
    if isinstance(event, Message):
        args = event.text.split()
        if len(args) < 2:
            await event.answer("❌ Usage: `/reject <order_id>`")
            return
        try:
            order_id = int(args[1])
        except ValueError:
            await event.answer("❌ Invalid order ID!")
            return
        message = event
    else:
        order_id = int(event.data.split("_")[1])
        message = event.message
    
    order = await db.get_order(order_id)
    
    if not order:
        await message.answer("❌ Order not found!")
        return
    
    if order['status'] != 'pending':
        await message.answer(f"⚠️ Order is already {order['status']}!")
        return
    
    await db.update_order_status(order_id, 'rejected')
    
    # Notify user
    try:
        await message.bot.send_message(
            order['telegram_id'],
            f"❌ **Order Rejected** \n\n"
            f"Order: `{order['order_number']}`\n"
            f"Coupon: {order['coupon_name']}\n\n"
            f"Payment verification failed. Contact support if needed."
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")
    
    await message.answer(
        f"❌ **Order Rejected** \n\n"
        f"Order ID: #{order_id}\n"
        f"User: @{order['username']}\n\n"
        f"User notified.",
        reply_markup=admin_menu_keyboard()
    )


@admin_router.message(Command("stats"))
async def show_stats(message: Message):
    """Show statistics"""
    if not is_admin(message.from_user.id):
        return
    
    users = await db.get_all_users()
    coupons = await db.get_all_coupons()
    all_orders = await db.get_all_orders()
    pending = await db.get_all_orders('pending')
    delivered = await db.get_all_orders('delivered')
    
    total_revenue = sum(o['total_price'] for o in delivered)
        
    total_codes = 0
    available_codes = 0
    for coupon in coupons:
        total, available = await db.get_code_count(coupon['id'])
        total_codes += total
        available_codes += available
    
    stats_text = f"""
📊 **Bot Statistics** 
👥 **Users:** {len(users)}
📦 **Coupons:** {len(coupons)}
🎫 **Total Codes:** {total_codes}
✅ **Available Codes:** {available_codes}

📋 **Orders:**    • Total: {len(all_orders)}
   • Pending: {len(pending)}
   • Delivered: {len(delivered)}

💰 **Revenue:** ₹{total_revenue:.2f}
 **Low Stock Alerts:** """
    
    low_stock_items = []
    for coupon in coupons:
        if coupon['stock'] <= LOW_CODE_THRESHOLD:
            low_stock_items.append(f"⚠️ {coupon['name']}: {coupon['stock']} left")
    
    if low_stock_items:
        stats_text += "\n" + "\n".join(low_stock_items)
    else:
        stats_text += "\n✅ All coupons have sufficient stock"
    
    await message.answer(stats_text)


@admin_router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Start broadcast"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await state.set_state(AdminState.broadcasting)
    await callback.message.edit_text(
        "📢 **Broadcast Message** \n\n"
        "Send the message to broadcast to all users:",
        reply_markup=back_to_admin_keyboard()
    )
    await callback.answer()


@admin_router.message(AdminState.broadcasting)
async def process_broadcast(message: Message, state: FSMContext):
    """Process broadcast"""
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text or message.caption
    
    if not broadcast_text:
        await message.answer("❌ Message cannot be empty!")
        return
    
    users = await db.get_all_users()
    
    if not users:
        await message.answer("❌ No users found!")
        await state.clear()
        return
    
    progress_msg = await message.answer(f"📤 Broadcasting to {len(users)} users...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await message.bot.send_message(user_id, broadcast_text)
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            failed += 1
    
    await progress_msg.edit_text(
        f"✅ **Broadcast Complete!** \n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {len(users)}",
        reply_markup=admin_menu_keyboard()
    )
    
    await state.clear()


@admin_router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Admin settings"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    current_upi = await db.get_setting('upi_id')
    if not current_upi:
        current_upi = UPI_ID
    
    text = f"""
⚙️ **Admin Settings**  **Current UPI ID:** `{current_upi}`
 **Commands:** • `/setupi <upi_id>` - Change UPI
• `/add <name> <price>` - Add coupon
• `/addcodes <coupon>` - Add codes
• `/approve <id>` - Approve order
• `/reject <id>` - Reject order
• `/stats` - View statistics
"""
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
    await callback.answer()


@admin_router.message(Command("setupi"))
async def set_upi(message: Message):
    """Set UPI ID"""
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Usage: `/setupi <upi_id>`\n\nExample: `/setupi merchant@paytm`")
        return
    
    new_upi = args[1].strip()
    
    if '@' not in new_upi:
        await message.answer("❌ Invalid UPI ID! Must contain '@'")
        return
    
    await db.set_setting('upi_id', new_upi)
    
    await message.answer(
        f"✅ **UPI ID Updated!** \n\nNew UPI: `{new_upi}`",
        reply_markup=admin_menu_keyboard()
    )


@admin_router.callback_query(F.data == "admin_add_coupon")
async def add_coupon_callback(callback: CallbackQuery):
    """Add coupon via callback"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ **Add New Coupon** \n\n"
        "Use command: `/add <name> <price>`\n\n"
        "Example: `/add Netflix499 499`",
        reply_markup=back_to_admin_keyboard()
    )
    await callback.answer()