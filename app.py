import os
import json
import base64
import warnings
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from groq import Groq
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import *

warnings.filterwarnings('ignore')  # Suppress warnings

# Load from environment variables
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

if not GROQ_API_KEY or not TELEGRAM_TOKEN:
    raise ValueError("GROQ_API_KEY and TELEGRAM_TOKEN must be set as environment variables")

client = Groq(api_key=GROQ_API_KEY)

# Google Sheets Setup
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
credentials_json = os.environ.get('CREDENTIALS_JSON')
if not credentials_json:
    raise ValueError("CREDENTIALS_JSON must be set as environment variable with the service account JSON")
creds_dict = json.loads(credentials_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)
sheet = gc.open("My Expenses 2025").sheet1

# Predefined Investors
INVESTORS = ["Vikas Uppal", "Anupam K", "Prasanna Patel", "Akhilesh", "Shashank", "Other (Type Name)"]

# Conversation states
AWAITING_INVESTOR, AWAITING_CUSTOM_NAME = range(2)

# Store temporary data
user_data = {}

# Setup headers with formatting
headers = ['Date', 'Investor/Person', 'Merchant', 'Total', 'Currency', 'Category', 'Description', 'Items', 'Tax', 'Subtotal', 'Receipt Number', 'Image Link']
current_headers = sheet.row_values(1) if sheet.row_count > 0 else []

if current_headers != headers:
    sheet.clear()
    sheet.append_row(headers)

    # Apply beautiful formatting to headers
    header_format = CellFormat(
        backgroundColor=Color(0.2, 0.4, 0.7),  # Blue background
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1), fontSize=11),
        horizontalAlignment='CENTER'
    )
    format_cell_range(sheet, 'A1:L1', header_format)

    # Set column widths
    set_column_width(sheet, 'A', 120)  # Date
    set_column_width(sheet, 'B', 150)  # Investor
    set_column_width(sheet, 'C', 180)  # Merchant
    set_column_width(sheet, 'D:E', 100)  # Total, Currency
    set_column_width(sheet, 'F', 130)  # Category
    set_column_width(sheet, 'G', 250)  # Description
    set_column_width(sheet, 'H', 300)  # Items
    set_column_width(sheet, 'I:K', 100)  # Tax, Subtotal, Receipt#
    set_column_width(sheet, 'L', 200)  # Image Link

print("✅ CONNECTED & HEADERS SET WITH FORMATTING!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Expense Tracker Bot!*\n\n"
        "📸 Upload a receipt and I'll:\n"
        "1️⃣ Ask who made the purchase\n"
        "2️⃣ Extract all details (merchant, items, total, tax, etc.)\n"
        "3️⃣ Store the receipt image link\n"
        "4️⃣ Save everything to Google Sheets with colors!\n\n"
        "✅ *Supported formats:* Photos, JPG, PNG, PDF, WEBP, GIF\n"
        "📎 Send as photo or file - both work!\n\n"
        "Let's get started! 🚀",
        parse_mode='Markdown'
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Handle both photos and document images
    if update.message.photo:
        file_obj = update.message.photo[-1]
        file_type = "photo"
    elif update.message.document:
        file_obj = update.message.document
        file_type = "document"
    else:
        await update.message.reply_text("❌ Please send an image file (JPG, PNG, PDF, etc.)")
        return ConversationHandler.END

    user_data[user_id] = {
        'file': file_obj,
        'file_type': file_type,
        'message': update.message
    }

    # Create inline keyboard with investor options (2 buttons per row)
    keyboard = [
        [InlineKeyboardButton(INVESTORS[0], callback_data="inv_0"),
         InlineKeyboardButton(INVESTORS[1], callback_data="inv_1")],
        [InlineKeyboardButton(INVESTORS[2], callback_data="inv_2"),
         InlineKeyboardButton(INVESTORS[3], callback_data="inv_3")],
        [InlineKeyboardButton(INVESTORS[4], callback_data="inv_4"),
         InlineKeyboardButton(INVESTORS[5], callback_data="inv_5")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 *Who made this purchase?*\n\nSelect from the list or choose 'Other' to type a name:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return AWAITING_INVESTOR

async def investor_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    inv_index = int(query.data.split('_')[1])

    if inv_index == 5:  # "Other" selected
        await query.edit_message_text("✍️ Please type the person's name:")
        return AWAITING_CUSTOM_NAME
    else:
        investor_name = INVESTORS[inv_index]
        await process_receipt(update, context, investor_name, user_id, query)
        return ConversationHandler.END

async def custom_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    investor_name = update.message.text.strip()

    if not investor_name:
        await update.message.reply_text("❌ Name cannot be empty. Please try again:")
        return AWAITING_CUSTOM_NAME

    await process_receipt(update, context, investor_name, user_id, None)
    return ConversationHandler.END

async def process_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, investor_name: str, user_id: int, query=None):
    # Get stored file data
    file_data = user_data.get(user_id)
    if not file_data:
        msg = "❌ Error: File data not found. Please upload the receipt again."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    file_obj = file_data['file']
    file_type = file_data['file_type']
    original_message = file_data['message']

    # Send processing message
    if query:
        await query.edit_message_text(f"🔍 Processing receipt for *{investor_name}*...\n⏳ Extracting details (10-20 sec)", parse_mode='Markdown')
        reply_to = query.message
    else:
        reply_to = await update.message.reply_text(f"🔍 Processing receipt for *{investor_name}*...\n⏳ Extracting details (10-20 sec)", parse_mode='Markdown')

    # Download and encode image
    file = await file_obj.get_file()

    # Determine file extension
    if file_type == "document":
        file_name = file_obj.file_name or "receipt.jpg"
        file_ext = file_name.split('.')[-1].lower()
    else:
        file_ext = "jpg"

    file_path = f"receipt_{user_id}.{file_ext}"
    await file.download_to_drive(file_path)

    # Get Telegram file link
    image_link = file.file_path

    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    # Determine MIME type
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'pdf': 'application/pdf'
    }
    mime_type = mime_types.get(file_ext, 'image/jpeg')

    # OCR: Extract raw text with better error handling
    try:
        ocr = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role":"user","content":[
                {"type":"text","text":"Extract EVERY word, number, and line exactly as it appears on this receipt/invoice. Include ALL details like merchant, address, date, items, quantities, prices, totals, tax, subtotal. Return ONLY the raw extracted text—no explanations or formatting."},
                {"type":"image_url","image_url":{"url":f"data:{mime_type};base64,{b64}"}}
            ]}],
            max_tokens=2000,
            temperature=0.1
        )
        raw_text = ocr.choices[0].message.content.strip()

        # Check if extraction was successful
        if not raw_text or len(raw_text) < 10:
            raise ValueError("No text extracted from image")

    except Exception as e:
        error_msg = f"⚠️ Could not extract text from image. Error: {str(e)}\n\nPlease try:\n1. Taking a clearer photo\n2. Better lighting\n3. Flattening the receipt"
        if query:
            await query.edit_message_text(error_msg)
        else:
            await reply_to.edit_text(error_msg)

        # Clean up
        if user_id in user_data:
            del user_data[user_id]
        if os.path.exists(file_path):
            os.remove(file_path)
        return

    # Parse with AI
    cat_prompt = f'''You are an expert at parsing receipts. Analyze this raw text and return ONLY valid JSON—no extra text, no markdown, just the JSON object.

Extract ALL important details accurately. Use these exact keys:

{{
  "merchant": "exact merchant name",
  "date": "YYYY-MM-DD format (convert if needed, if not found use today's date)",
  "total": number like 724.50 (extract from total/grand total/amount),
  "currency": "INR or USD or from text (default INR for Indian receipts)",
  "category": one of "Meals|Travel|Office Supplies|Software|Entertainment|Other",
  "description": "brief 1-sentence summary",
  "items": "semicolon-separated list e.g. 'White Basic Tank Top: 2 x $100.00 = $200.00; Denim Jacket: 5 x $50.00 = $250.00'",
  "tax": number like 34.50 (GST/VAT/Tax amount),
  "subtotal": number like 690.00,
  "receipt_number": "invoice/receipt number if available, else empty"
}}

IMPORTANT:
- If merchant not clear, look for shop/company name at top
- Total is usually the largest number or labeled as "Total/Grand Total/Amount"
- For Indian receipts, currency is INR by default
- Extract numbers carefully, don't return 0 if there's a valid amount

Raw text:
{raw_text}'''

    cat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role":"user","content": cat_prompt}],
        max_tokens=800,
        temperature=0.1
    )
    response_text = cat.choices[0].message.content.strip()

    # Parse JSON with fallback
    try:
        # Remove markdown if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        data = json.loads(response_text)

        # Validate that we got useful data
        if data.get("merchant") == "Parse Error" or data.get("total", 0) == 0:
            raise ValueError("Insufficient data extracted")

    except (json.JSONDecodeError, ValueError) as e:
        # Fallback: Ask AI to fix JSON
        fix_prompt = f"Fix this into valid JSON only: {response_text}. Use the exact keys from the prompt above. Make sure to extract merchant name and total amount from this text: {raw_text[:500]}"
        fix = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":fix_prompt}], max_tokens=500, temperature=0.1)
        try:
            fix_text = fix.choices[0].message.content.strip()
            if "```json" in fix_text:
                fix_text = fix_text.split("```json")[1].split("```")[0].strip()
            elif "```" in fix_text:
                fix_text = fix_text.split("```")[1].split("```")[0].strip()
            data = json.loads(fix_text)
        except:
            # Last resort: Save raw text for manual review
            data = {
                "merchant": "Manual Review Needed",
                "date": "2025-12-06",
                "total": 0,
                "currency": "INR",
                "category": "Other",
                "description": f"Auto-extraction failed. Raw: {raw_text[:150]}",
                "items": raw_text[:300] if len(raw_text) > 0 else "No text extracted",
                "tax": 0,
                "subtotal": 0,
                "receipt_number": ""
            }

    # Prepare row with investor name
    row = [
        data.get("date", ""),
        investor_name,  # New column
        data.get("merchant", ""),
        data.get("total", 0),
        data.get("currency", "USD"),
        data.get("category", ""),
        data.get("description", ""),
        data.get("items", ""),
        data.get("tax", 0),
        data.get("subtotal", 0),
        data.get("receipt_number", ""),
        image_link  # Store image link
    ]

    # Append to sheet
    sheet.append_row(row)
    row_number = len(sheet.get_all_values())

    # Apply alternating row colors
    if row_number % 2 == 0:
        row_color = Color(0.95, 0.95, 0.95)  # Light gray
    else:
        row_color = Color(1, 1, 1)  # White

    row_format = CellFormat(backgroundColor=row_color)
    format_cell_range(sheet, f'A{row_number}:L{row_number}', row_format)

    # Format currency columns
    currency_format = CellFormat(numberFormat=NumberFormat(type='CURRENCY', pattern='$#,##0.00'))
    format_cell_range(sheet, f'D{row_number}', currency_format)  # Total
    format_cell_range(sheet, f'I{row_number}:J{row_number}', currency_format)  # Tax, Subtotal

    # Success message
    if data.get("merchant") == "Manual Review Needed" or data.get("total", 0) == 0:
        success_msg = (
            f"⚠️ *Receipt Saved - Manual Review Needed*\n\n"
            f"👤 *Person:* {investor_name}\n"
            f"🏪 *Merchant:* {data.get('merchant', 'N/A')}\n"
            f"💰 *Total:* {data.get('currency', 'INR')} {data.get('total', 0)}\n"
            f"📅 *Date:* {data.get('date', 'N/A')}\n"
            f"📂 *Category:* {data.get('category', 'N/A')}\n"
            f"🔗 *Image:* [View Receipt]({image_link})\n\n"
            f"❗ *Extracted Text:*\n`{raw_text[:200]}...`\n\n"
            f"⚠️ Please review and update manually in Google Sheets.\n"
            f"Try uploading a clearer image if possible."
        )
    else:
        success_msg = (
            f"✅ *Receipt Saved Successfully!*\n\n"
            f"👤 *Person:* {investor_name}\n"
            f"🏪 *Merchant:* {data.get('merchant', 'N/A')}\n"
            f"💰 *Total:* {data.get('currency', 'INR')} {data.get('total', 0)}\n"
            f"📅 *Date:* {data.get('date', 'N/A')}\n"
            f"📂 *Category:* {data.get('category', 'N/A')}\n"
            f"🔗 *Image:* [View Receipt]({image_link})\n\n"
            f"✨ All details saved to Google Sheets with formatting!"
        )

    if query:
        await reply_to.edit_text(success_msg, parse_mode='Markdown')
    else:
        await reply_to.edit_text(success_msg, parse_mode='Markdown')

    # Clean up
    if user_id in user_data:
        del user_data[user_id]
    if os.path.exists(file_path):
        os.remove(file_path)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Upload a receipt to start again!")
    return ConversationHandler.END

# Build application
app = Application.builder().token(TELEGRAM_TOKEN).build()

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.PHOTO, handle_image),
        MessageHandler(filters.Document.IMAGE | filters.Document.PDF, handle_image)
    ],
    states={
        AWAITING_INVESTOR: [CallbackQueryHandler(investor_selected, pattern="^inv_")],
        AWAITING_CUSTOM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_name_received)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(conv_handler)

print("🚀 ENHANCED BOT READY WITH INVESTOR TRACKING!")
print("📱 Open Telegram and send a receipt (photo/file - JPG/PNG/PDF/WEBP)!")
app.run_polling(drop_pending_updates=True)