from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import *
from utils import *
from config import ADMIN_IDS, LOW_CODE_THRESHOLD
import logging
import aiosqlite

logger = logging.getLogger(__name__)
admin_router = Router()


# Admin state groups
class AdminState(StatesGroup):
    adding_coupon_name = State()
    adding_coupon_price = State()
    adding_codes_coupon = State()
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


# Add Coupon Flow
@admin_router.callback_query(F.data == "admin_add_coupon")
async def add_coupon_start(callback: CallbackQuery, state: FSMContext):
    """Start add coupon flow"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await state.set_state(AdminState.adding_coupon_name)
    await callback.message.edit_text(
        "➕ **Add New Coupon** \n\nEnter coupon name:",
        reply_markup=back_to_admin_keyboard()
    )
    await callback.answer()


@admin_router.message(AdminState.adding_coupon_name)
async def add_coupon_name(message: Message, state: FSMContext):
    """Process coupon name"""
    if not is_admin(message.from_user.id):
        return
    
    coupon_name = message.text.strip()
    
    if len(coupon_name) < 3:
        await message.answer("❌ Coupon name must be at least 3 characters!")
        return
    
    await state.update_data(coupon_name=coupon_name)
    await state.set_state(AdminState.adding_coupon_price)
    
    await message.answer(
        f"Coupon Name: **{coupon_name}** \n\nNow enter the price (₹):",
        reply_markup=cancel_keyboard()
    )


@admin_router.message(AdminState.adding_coupon_price)
async def add_coupon_price(message: Message, state: FSMContext):
    """Process coupon price and create coupon"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        price = float(message.text.strip())
        if price <= 0:
            await message.answer("❌ Price must be greater than 0!")
            return
    except ValueError:
        await message.answer("❌ Invalid price! Enter a number (e.g., 99 or 149.50)")
        return
    
    data = await state.get_data()
    coupon_name = data['coupon_name']
    
    # Add coupon to database
    success = await db.add_coupon(coupon_name, price)
    
    if success:
        await message.answer(
            f"✅ **Coupon Created Successfully!** \n\n"
            f"Name: {coupon_name}\n"
            f"Price: ₹{price}\n\n"
            f"⚠️ Don't forget to add coupon codes using:\n"
            f"`/addcodes {coupon_name}`",
            reply_markup=admin_menu_keyboard()
        )
    else:
        await message.answer(
            f"❌ Coupon '{coupon_name}' already exists!",
            reply_markup=admin_menu_keyboard()
        )
    
    await state.clear()


# Add Coupon Codes
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
        f"`CODE-DEF-456`\n"
        f"`CODE-GHI-789`\n\n"
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


# Manage Stock
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
    
    text += f"\n_Add codes using: `/addcodes <coupon_name>`_"
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
    await callback.answer()


# View Orders
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
    
    for order in orders[:15]:  # Show last 15 orders
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
        text += f"   UTR: `{order['utr']}`\n"
        text += f"   Status: {order['status'].upper()}\n\n"
    
    if len(orders) > 15:
        text += f"\n_Showing 15 of {len(orders)} orders_\n"
    
    text += f"\n💡 Use `/approve <order_id>` or `/reject <order_id>`"
    
    await callback.message.edit_text(text, reply_markup=order_status_keyboard())
    await callback.answer()


# Approve Order
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
    else:  # CallbackQuery
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
    
    # Check if enough codes are available
    available_codes = await db.get_available_codes(order['coupon_id'], order['quantity'])
    
    if len(available_codes) < order['quantity']:
        await message.answer(
            f"❌ **Insufficient Coupon Codes!** \n\n"
            f"Required: {order['quantity']} codes\n"
            f"Available: {len(available_codes)} codes\n\n"
            f"Please add more codes using:\n"
            f"`/addcodes {order['coupon_name']}`"
        )
        return
    
    try:
        # Fetch required codes
        codes_to_deliver = available_codes[:order['quantity']]
        
        # Mark codes as used
        await db.mark_codes_as_used(
            order['coupon_id'],
            codes_to_deliver,
            order['user_id']
        )
        
        # Update order status to delivered
        await db.update_order_status(order_id, 'delivered')
        
        # Send codes to user
        codes_message = format_codes_message(codes_to_deliver)
        order_info = f"📦 Order: `{order['order_number']}`\n"
        order_info += f"Coupon: **{order['coupon_name']}** \n\n"
        
        full_message = order_info + codes_message
        
        try:
            await message.bot.send_message(
                order['telegram_id'],
                full_message
            )
            
            delivery_status = "✅ Codes delivered to user!"
        except Exception as e:
            logger.error(f"Failed to send codes to user: {e}")
            delivery_status = "⚠️ Failed to send codes to user directly!"
        
        # Confirm to admin
        confirmation = f"""
✅ **Order Approved & Delivered!** 
Order ID: #{order_id}
Order Number: `{order['order_number']}`
User: @{order['username']} (ID: {order['telegram_id']})
Coupon: {order['coupon_name']}
Quantity: {order['quantity']}
Codes Delivered: {len(codes_to_deliver)}

{delivery_status}
"""
        
        await message.answer(confirmation, reply_markup=admin_menu_keyboard())
        
        # Check for low stock
        coupon = await db.get_coupon_by_id(order['coupon_id'])
        if coupon and coupon['stock'] <= LOW_CODE_THRESHOLD:
            await message.answer(
                f"⚠️ **Low Stock Alert!** \n\n"
                f"Coupon: {coupon['name']}\n"
                f"Remaining: {coupon['stock']} codes\n\n"
                f"Please add more codes soon!"
            )
        
    except Exception as e:
        logger.error(f"Error approving order: {e}")
        await message.answer(f"❌ Error approving order: {str(e)}")


# Reject Order
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
    else:  # CallbackQuery
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
    
    # Update order status
    await db.update_order_status(order_id, 'rejected')
    
    # Notify user
    try:
        await message.bot.send_message(
            order['telegram_id'],
            f"❌ **Order Rejected** \n\n"
            f"Order Number: `{order['order_number']}`\n"
            f"Coupon: {order['coupon_name']}\n\n"
            f"Your payment verification failed. Please contact support if you believe this is an error."
        )
    except Exception as e:
        logger.error(f"Failed to notify user about rejection: {e}")
    
    # Confirm to admin
    await message.answer(
        f"❌ **Order Rejected** \n\n"
        f"Order ID: #{order_id}\n"
        f"User: @{order['username']}\n\n"
        f"User has been notified.",
        reply_markup=admin_menu_keyboard()
    )


# Broadcast
@admin_router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Start broadcast message"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    await state.set_state(AdminState.broadcasting)
    await callback.message.edit_text(
        "📢 **Broadcast Message** \n\n"
        "Send the message you want to broadcast to all users:",
        reply_markup=back_to_admin_keyboard()
    )
    await callback.answer()


@admin_router.message(AdminState.broadcasting)
async def process_broadcast(message: Message, state: FSMContext):
    """Process and send broadcast"""
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text or message.caption
    
    if not broadcast_text:
        await message.answer("❌ Message cannot be empty!")
        return
    
    users = await db.get_all_users
    ()
    
    if not users:
        await message.answer("❌ No users found!")
        await state.clear()
        return
    
    # Send broadcast
    progress_msg = await message.answer(f"📤 Broadcasting to {len(users)} users...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await message.bot.send_message(user_id, broadcast_text)
            success += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            failed += 1
    
    await progress_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {len(users)}",
        reply_markup=admin_menu_keyboard()
    )
    
    await state.clear()


# Admin Settings
@admin_router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Show admin settings"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    # Get current UPI ID from database
    current_upi = await db.get_setting('upi_id')
    if not current_upi:
        current_upi = UPI_ID
    
    text = f"""
⚙️ **Admin Settings**

**Current UPI ID:** `{current_upi}`

To change UPI ID, use:
`/setupi <new_upi_id>`

**Other Commands:**
• `/stats` - View statistics
• `/add <name> <price>` - Quick add coupon
• `/addcodes <coupon>` - Add coupon codes
• `/approve <order_id>` - Approve order
• `/reject <order_id>` - Reject order
"""
    
    await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
    await callback.answer()


@admin_router.message(Command("setupi"))
async def set_upi(message: Message):
    """Set new UPI ID"""
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Usage: `/setupi <upi_id>`\n\nExample: `/setupi merchant@paytm`")
        return
    
    new_upi = args[1].strip()
    
    if '@' not in new_upi:
        await message.answer("❌ Invalid UPI ID format! Must contain '@'")
        return
    
    await db.set_setting('upi_id', new_upi)
    
    await message.answer(
        f"✅ **UPI ID Updated!**\n\nNew UPI ID: `{new_upi}`\n\n"
        f"This will be used for all new orders.",
        reply_markup=admin_menu_keyboard()
    )


@admin_router.message(Command("add"))
async def quick_add_coupon(message: Message):
    """Quick add coupon command"""
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
            f"✅ **Coupon Created!**\n\n"
            f"Name: {coupon_name}\n"
            f"Price: ₹{price}\n\n"
            f"Now add codes using:\n"
            f"`/addcodes {coupon_name}`"
        )
    else:
        await message.answer(f"❌ Coupon '{coupon_name}' already exists!")


@admin_router.message(Command("stats"))
async def show_stats(message: Message):
    """Show bot statistics"""
    if not is_admin(message.from_user.id):
        return
    
    # Get statistics
    users = await db.get_all_users()
    coupons = await db.get_all_coupons()
    all_orders = await db.get_all_orders()
    pending_orders = await db.get_all_orders('pending')
    approved_orders = await db.get_all_orders('delivered')
    
    # Calculate total revenue
    total_revenue = sum(order['total_price'] for order in approved_orders)
    
    # Get total codes
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

📋 **Orders:**
   • Total: {len(all_orders)}
   • Pending: {len(pending_orders)}
   • Delivered: {len(approved_orders)}

💰 **Revenue:** ₹{total_revenue:.2f}

**Low Stock Alerts:**
"""
    
    # Check low stock
    low_stock_items = []
    for coupon in coupons:
        if coupon['stock'] <= LOW_CODE_THRESHOLD:
            low_stock_items.append(f"⚠️ {coupon['name']}: {coupon['stock']} codes left")
    
    if low_stock_items:
        stats_text += "\n" + "\n".join(low_stock_items)
    else:
        stats_text += "\n✅ All coupons have sufficient stock"
    
    await message.answer(stats_text)