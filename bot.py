"""
Interior Estimate POC Bot (Telegram)

Flow:
  Upload floor plan image
  -> Agent 1 estimates area using GPT-4.1 mini vision
  -> User confirms whether sqft estimate is correct
  -> If incorrect, user enters sqft manually
  -> Pick style tier
  -> Pick budget range
  -> Agent 2 computes mocked estimate
  -> Branch message based on estimate vs budget
  -> CTA buttons
"""

import os
import re
import base64
import logging

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

from pricing import STYLE_TIERS, BUDGET_RANGES, estimate_cost, compare_to_budget

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

OPENAI_MODEL = "gpt-4.1-mini"

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Conversation states
WAITING_IMAGE, CONFIRM_AREA, MANUAL_AREA, ASK_STYLE, ASK_BUDGET, POST_ESTIMATE, DEAD_END = range(7)


# ---------- Agent 1: floor plan -> rough area estimate ----------

def estimate_area_from_image(image_bytes: bytes, media_type: str) -> float:
    """
    Sends the floor plan to GPT-4.1 mini and asks for a rough sqft estimate.

    This is intentionally approximate.
    Vision models cannot precisely measure floor plans every time,
    so the user gets a chance to confirm or manually correct the sqft.
    """

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:{media_type};base64,{base64_image}"

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are analyzing a residential floor plan image. "
                            "Your task is to estimate the total carpet area or usable interior area "
                            "in square feet. Use any visible dimensions, room labels, scale markings, "
                            "and typical room proportions. "
                            "If the plan contains room dimensions, calculate the approximate total area "
                            "by adding the visible room areas. "
                            "If exact dimensions are not visible, give your best rough estimate. "
                            "Return ONLY one number. "
                            "Do not include units. "
                            "Do not include commas. "
                            "Do not include words. "
                            "Do not explain. "
                            "Example response: 1250"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "high",
                    },
                ],
            }
        ],
        max_output_tokens=50,
    )

    text = response.output_text or ""

    logger.info("OpenAI raw sqft response: %s", text)

    match = re.search(r"\d+(\.\d+)?", text.replace(",", ""))

    if not match:
        return 1200.0

    return float(match.group())


# ---------- Helper: show style options ----------

async def show_style_options_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Sends style options after sqft has been confirmed or manually entered.
    Used when responding to a normal user message.
    """

    keyboard = [
        [
            InlineKeyboardButton(
                tier["label"],
                callback_data=f"style:{key}",
            )
        ]
        for key, tier in STYLE_TIERS.items()
    ]

    await update.message.reply_text(
        "Which style best matches the home you'd love to build?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return ASK_STYLE


async def show_style_options_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Sends style options after clicking the area confirmation button.
    Used when responding to an inline button click.
    """

    query = update.callback_query

    keyboard = [
        [
            InlineKeyboardButton(
                tier["label"],
                callback_data=f"style:{key}",
            )
        ]
        for key, tier in STYLE_TIERS.items()
    ]

    await query.edit_message_text(
        "Which style best matches the home you'd love to build?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return ASK_STYLE


# ---------- Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Starts the conversation.
    """

    context.user_data.clear()

    await update.message.reply_text(
        "Welcome! Let's estimate your interior fit-out cost.\n\n"
        "Upload a photo of your floor plan (JPEG/PNG) to get started."
    )

    return WAITING_IMAGE


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles floor plan upload.

    User uploads a photo/document.
    Bot sends it to GPT-4.1 mini.
    Bot shows estimated sqft.
    Bot asks whether the sqft estimate is correct.
    """

    photo = update.message.photo[-1] if update.message.photo else None
    document = update.message.document

    if not photo and not document:
        await update.message.reply_text(
            "Please upload a floor plan image to continue."
        )
        return WAITING_IMAGE

    file_obj = await (photo or document).get_file()
    image_bytes = await file_obj.download_as_bytearray()

    media_type = "image/jpeg"

    if document and document.mime_type:
        media_type = document.mime_type

    await update.message.reply_text(
        "Got it! Analyzing your floor plan..."
    )

    try:
        area = estimate_area_from_image(
            bytes(image_bytes),
            media_type,
        )

    except Exception:
        logger.exception("Agent 1 image estimation failed")

        await update.message.reply_text(
            "I had trouble reading that image.\n\n"
            "Let's use a placeholder estimate for this demo."
        )

        area = 1200.0

    context.user_data["estimated_area"] = area

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Yes, this is correct",
                callback_data="area:yes",
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ No, I'll enter it manually",
                callback_data="area:no",
            )
        ],
    ]

    await update.message.reply_text(
        f"We estimate your home is approximately {int(area)} sq ft.\n\n"
        "Is this correct?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return CONFIRM_AREA


async def confirm_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles user confirmation of GPT-4.1 mini's sqft estimate.
    """

    query = update.callback_query
    await query.answer()

    choice = query.data

    if choice == "area:yes":
        context.user_data["area_sqft"] = context.user_data["estimated_area"]

        return await show_style_options_query(update, context)

    await query.edit_message_text(
        "No problem.\n\n"
        "Please enter your home's approximate area in sqft.\n\n"
        "Example: 1500"
    )

    return MANUAL_AREA


async def manual_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles manual sqft entry.
    """

    text = update.message.text.strip()

    match = re.search(r"\d+(\.\d+)?", text.replace(",", ""))

    if not match:
        await update.message.reply_text(
            "Please enter only the area as a number.\n\n"
            "Example: 1500"
        )
        return MANUAL_AREA

    sqft = float(match.group())

    if sqft <= 0:
        await update.message.reply_text(
            "Please enter a valid sqft area greater than 0."
        )
        return MANUAL_AREA

    context.user_data["area_sqft"] = sqft

    await update.message.reply_text(
        f"Got it. We'll use {int(sqft)} sq ft for the estimate."
    )

    return await show_style_options_message(update, context)


async def handle_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles style tier selection.
    """

    query = update.callback_query
    await query.answer()

    style_key = query.data.split(":", 1)[1]

    context.user_data["style_key"] = style_key

    tier = STYLE_TIERS[style_key]

    keyboard = [
        [
            InlineKeyboardButton(
                budget["label"],
                callback_data=f"budget:{key}",
            )
        ]
        for key, budget in BUDGET_RANGES.items()
    ]

    await query.edit_message_text(
        f"Style selected: {tier['label']} — {tier['tagline']}\n\n"
        "Which investment feels comfortable for your home interiors?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return ASK_BUDGET


async def handle_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles budget selection.
    Generates estimate.
    Compares estimate against budget.
    Sends branch-specific response.
    """

    query = update.callback_query
    await query.answer()

    budget_key = query.data.split(":", 1)[1]

    context.user_data["budget_key"] = budget_key

    await query.edit_message_text("Crunching the numbers...")

    area = context.user_data["area_sqft"]
    style_key = context.user_data["style_key"]

    result = estimate_cost(area, style_key)

    context.user_data["estimate"] = result

    scope_text = "\n".join(
        f"- {item}"
        for item in result["scope"]
    )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "We've estimated the following scope:\n\n"
            f"{scope_text}\n\n"
            f"Estimated Investment: ₹{result['estimated_investment_lakhs']} Lakhs\n"
            f"Confidence: {result['confidence']}%"
        ),
    )

    comparison = compare_to_budget(
        result["estimated_investment"],
        budget_key,
    )

    context.user_data["comparison"] = comparison

    if comparison == "over":
        text = (
            "We noticed something...\n\n"
            "The style you selected and the scope we've identified come to "
            f"approximately ₹{result['estimated_investment_lakhs']} lakh, which is above "
            "what you were expecting.\n\n"
            "The good news is that this is usually easy to optimize. Our interior "
            "experts can suggest smarter alternatives, adjust the scope, recommend "
            "different materials, or phase the project without compromising the "
            "overall look and feel of your home.\n\n"
            "Would you like us to help you build a design that fits your budget?"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "Yes, let's talk",
                    callback_data="cta:consult",
                )
            ],
            [
                InlineKeyboardButton(
                    "Show ways to reduce cost",
                    callback_data="cta:reduce_cost",
                )
            ],
            [
                InlineKeyboardButton(
                    "I'll explore later",
                    callback_data="end:explore_later",
                )
            ],
        ]

    elif comparison == "under":
        text = (
            "Good news!\n\n"
            "Your preferred style and selected scope come to approximately "
            f"₹{result['estimated_investment_lakhs']} lakh, which is comfortably within "
            "the investment range you had in mind.\n\n"
            "That gives you room to enhance your interiors with premium finishes, "
            "better storage solutions, designer lighting, or additional custom "
            "features if you'd like.\n\n"
            "Would you like our experts to show you what more is possible within "
            "your budget?"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "Show upgrade ideas",
                    callback_data="cta:upgrade",
                )
            ],
            [
                InlineKeyboardButton(
                    "Connect me with an expert",
                    callback_data="cta:consult",
                )
            ],
            [
                InlineKeyboardButton(
                    "I'm happy with this",
                    callback_data="end:happy",
                )
            ],
        ]

    elif comparison == "match":
        text = (
            "Looks like we're well aligned.\n\n"
            "Your preferred style and expected investment are a close match. The "
            "estimate we've generated should be a realistic starting point for your "
            "home.\n\n"
            "The next step is finding the right interior partner to bring it to life."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "Talk to an Expert",
                    callback_data="cta:consult",
                )
            ],
            [
                InlineKeyboardButton(
                    "Find Interior Partners",
                    callback_data="end:find_partners",
                )
            ],
            [
                InlineKeyboardButton(
                    "Download Estimate",
                    callback_data="end:download",
                )
            ],
        ]

    else:
        text = (
            "No problem — since you're not sure on budget yet, here's your estimate "
            "as a starting point. Our experts can help you figure out what fits."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "Talk to an Expert",
                    callback_data="cta:consult",
                )
            ],
            [
                InlineKeyboardButton(
                    "I'll explore later",
                    callback_data="end:explore_later",
                )
            ],
        ]

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return POST_ESTIMATE


async def handle_post_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles CTA buttons after estimate.
    """

    query = update.callback_query
    await query.answer()

    action = query.data

    if action.startswith("end:"):
        closing_messages = {
            "end:explore_later": "No worries — come back anytime you're ready. 👋",
            "end:happy": "Great to hear! Feel free to reach out whenever you're ready to move forward. 👋",
            "end:find_partners": "We'll share a shortlist of trusted interior partners shortly. 👋",
            "end:download": "Your estimate summary would be generated as a PDF here in the full version. 👋",
            "end:booked": "You're all set! In the full version, this would open a booking calendar. For this POC, consider this conversation complete. 🎉",
        }

        await query.edit_message_text(
            closing_messages.get(
                action,
                "Thanks for trying this out! 👋",
            )
        )

        return ConversationHandler.END

    if action == "cta:reduce_cost":
        await query.edit_message_text(
            "Here are typical ways we reduce cost without hurting the design:\n\n"
            "- Swap premium veneers for high-quality laminates\n"
            "- Phase non-essential rooms for later\n"
            "- Simplify false ceiling detailing\n\n"
            "Would you like to book a free consultation to go over specifics?"
        )

    elif action == "cta:upgrade":
        await query.edit_message_text(
            "Some popular upgrades within extra budget:\n\n"
            "- Designer lighting throughout\n"
            "- Premium hardware & soft-close fittings\n"
            "- Custom wardrobe interiors\n\n"
            "Would you like to book a free consultation to go over specifics?"
        )

    elif action == "cta:consult":
        await query.edit_message_text(
            "Great — the next step would be a short consultation with an interior expert."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "Book a Free Consultation",
                callback_data="end:booked",
            )
        ]
    ]

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "Let's help you make the right choice. A short 15-minute consultation "
            "can help you:\n\n"
            "✓ Validate this estimate\n"
            "✓ Understand where to spend and where to save\n"
            "✓ Compare different material options\n"
            "✓ Avoid common interior mistakes\n"
            "✓ Get matched with trusted interior partners near you\n\n"
            "No obligation. No sales pressure."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return POST_ESTIMATE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the conversation.
    """

    await update.message.reply_text(
        "Conversation cancelled. Send /start to try again."
    )

    return ConversationHandler.END


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
        ],
        states={
            WAITING_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    handle_image,
                )
            ],
            CONFIRM_AREA: [
                CallbackQueryHandler(
                    confirm_area,
                    pattern=r"^area:",
                )
            ],
            MANUAL_AREA: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    manual_area,
                )
            ],
            ASK_STYLE: [
                CallbackQueryHandler(
                    handle_style,
                    pattern=r"^style:",
                )
            ],
            ASK_BUDGET: [
                CallbackQueryHandler(
                    handle_budget,
                    pattern=r"^budget:",
                )
            ],
            POST_ESTIMATE: [
                CallbackQueryHandler(
                    handle_post_estimate,
                    pattern=r"^(cta:|end:)",
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    app.add_handler(conv_handler)

    print("🚀 Interior Estimate Bot is running...")
    logger.info("Bot starting...")

    app.run_polling()


if __name__ == "__main__":
    main()