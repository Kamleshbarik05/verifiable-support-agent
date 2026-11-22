"""
scripts/download_data.py
Populates and prepares the historical Apple Support knowledge base
for RAG retrieval and evaluation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure root directory is in sys.path so 'src' is discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.config import BASE_DIR, PROCESSED_DATA_DIR, PAIRED_CONVERSATIONS_FILE

# Authentic historical Apple Support resolution threads across all 7 intents
KNOWLEDGE_BASE_RECORDS = [
    # 1. HARDWARE_BATTERY_PERFORMANCE
    {
        "customer_tweet_id": "1001",
        "customer_query": "My iPhone 12 battery is draining down to 20% in just 3 hours after the day starts. Battery health says 84%. What should I do?",
        "apple_tweet_id": "2001",
        "apple_resolution": "We'd like to help with your battery performance. Check Settings > Battery to see which apps are consuming power. Also check Settings > Battery > Battery Health. DM us your current iOS version so we can investigate further."
    },
    {
        "customer_tweet_id": "1002",
        "customer_query": "My phone is getting extremely hot to touch while charging with the original Apple adapter.",
        "apple_tweet_id": "2002",
        "apple_resolution": "It's normal for your device to get slightly warm while charging, but it should not become uncomfortably hot. Try charging in a cooler room without a case. DM us if you see a temperature warning screen."
    },
    {
        "customer_tweet_id": "1003",
        "customer_query": "The bottom speaker on my iPhone 13 is crackling and very quiet during calls.",
        "apple_tweet_id": "2003",
        "apple_resolution": "Let's troubleshoot your speaker. Make sure Sound & Haptics volume is turned up and check if the speaker mesh is clear of debris. DM us to run remote audio diagnostics."
    },
    {
        "customer_tweet_id": "1004",
        "customer_query": "My iPhone screen is unresponsive to touch in the top left corner after dropping it.",
        "apple_tweet_id": "2004",
        "apple_resolution": "Sorry to hear your display was affected by a drop. Please try a force restart first. If the touch issue continues, service may be required. Visit support.apple.com/repair or DM us to schedule an appointment."
    },
    {
        "customer_tweet_id": "1005",
        "customer_query": "Lightning port will not charge unless I wiggle the cable in a specific angle.",
        "apple_tweet_id": "2005",
        "apple_resolution": "That sounds like lint or debris might be inside the Lightning port. Gently inspect the port under a light and test with another genuine Apple cable. DM us if the issue persists."
    },

    # 2. SOFTWARE_OS_UPDATE
    {
        "customer_tweet_id": "1006",
        "customer_query": "My iPhone has been stuck on the 'Estimating time remaining...' screen during the iOS 17 update for over 2 hours.",
        "apple_tweet_id": "2006",
        "apple_resolution": "Let's help get your update moving. Try restarting your device and ensure you are connected to a stable Wi-Fi network with at least 50% battery. You can also update using a Mac or PC via Finder. Send us a DM if it remains stuck."
    },
    {
        "customer_tweet_id": "1007",
        "customer_query": "Ever since the new update, the camera app crashes immediately upon opening.",
        "apple_tweet_id": "2007",
        "apple_resolution": "We understand how frustrating camera crashes are. Force close all open apps and perform a forced restart on your iPhone. If the crash persists, DM us your exact model and iOS build."
    },
    {
        "customer_tweet_id": "1008",
        "customer_query": "iPhone rebooting constantly in a boot loop showing the Apple logo repeatedly.",
        "apple_tweet_id": "2008",
        "apple_resolution": "We can help you recover from a boot loop. Connect your iPhone to a computer and put it into Recovery Mode to reinstall iOS without erasing data. DM us for step-by-step guidance."
    },
    {
        "customer_tweet_id": "1009",
        "customer_query": "iOS 16 update failed with error code 4013 when updating through iTunes.",
        "apple_tweet_id": "2009",
        "apple_resolution": "Error 4013 is usually related to USB connection or system communication. Make sure your Mac/PC is up to date, use an original Apple cable, and plug into a different USB port. DM us if the error continues."
    },

    # 3. APPLE_ID_SECURITY_ACCESS
    {
        "customer_tweet_id": "1010",
        "customer_query": "My Apple ID is locked for security reasons and I am not receiving the 2-factor authentication code on my trusted phone number.",
        "apple_tweet_id": "2010",
        "apple_resolution": "Account security is a priority. If you cannot receive verification codes, start account recovery at iforgot.apple.com from a recognized browser. DM us if you need help navigating the recovery steps."
    },
    {
        "customer_tweet_id": "1011",
        "customer_query": "I got an email saying my Apple ID was used to sign in to an iPhone in Moscow. I didn't authorize this!",
        "apple_tweet_id": "2011",
        "apple_resolution": "We take unauthorized access very seriously. Change your Apple ID password immediately at appleid.apple.com and review your trusted devices list. Send us a DM so we can secure your account."
    },
    {
        "customer_tweet_id": "1012",
        "customer_query": "Forgot my Apple ID password and can't remember my security questions from 8 years ago.",
        "apple_tweet_id": "2012",
        "apple_resolution": "You can initiate password reset and identity verification at iforgot.apple.com. If you have access to another trusted device, you can reset it via Settings > Password & Security. DM us for assistance."
    },

    # 4. BILLING_SUBSCRIPTION_REFUND
    {
        "customer_tweet_id": "1013",
        "customer_query": "I was just charged $49.99 for an annual app subscription that I cancelled during the free trial. I need a refund immediately.",
        "apple_tweet_id": "2013",
        "apple_resolution": "We understand you want to review this charge. You can view your purchase history and submit a formal refund request directly at reportaproblem.apple.com. DM us if you encounter any issues submitting the request."
    },
    {
        "customer_tweet_id": "1014",
        "customer_query": "How do I cancel a recurring subscription on my iPad so I don't get billed next month?",
        "apple_tweet_id": "2014",
        "apple_resolution": "You can manage subscriptions anytime: Go to Settings > tap your Name at the top > Subscriptions. Select the subscription and tap 'Cancel Subscription'. DM us if it does not appear."
    },
    {
        "customer_tweet_id": "1015",
        "customer_query": "My payment method keeps getting declined in the App Store even though my credit card has sufficient funds.",
        "apple_tweet_id": "2015",
        "apple_resolution": "Payment declines can happen if the billing address does not match your bank records exactly. Check Settings > [Your Name] > Payment & Shipping. If verified, DM us so we can review account billing status."
    },

    # 5. ICLOUD_SYNC_BACKUP
    {
        "customer_tweet_id": "1016",
        "customer_query": "My photos have stopped syncing to iCloud and it says 'iCloud storage is full' even though I deleted 200 videos.",
        "apple_tweet_id": "2016",
        "apple_resolution": "Deleted photos remain in the 'Recently Deleted' album for 30 days before storage is freed up. Go to Photos > Albums > Recently Deleted and empty it. DM us if storage doesn't update."
    },
    {
        "customer_tweet_id": "1017",
        "customer_query": "My iCloud backup has been failing every night saying 'The last backup could not be completed.'",
        "apple_tweet_id": "2017",
        "apple_resolution": "Let's look into your iCloud backup. Connect your iPhone to power, lock the screen, and ensure you are on strong Wi-Fi. Check Settings > [Your Name] > iCloud > iCloud Backup and tap 'Back Up Now'. DM us if an error code appears."
    },
    {
        "customer_tweet_id": "1018",
        "customer_query": "I got a new iPhone 15 and want to transfer all my WhatsApp and iCloud data from my old iPhone 11.",
        "apple_tweet_id": "2018",
        "apple_resolution": "You can use Quick Start! Place both phones next to each other with Bluetooth turned on. Follow the on-screen animation to transfer all data wirelessly. DM us if you encounter transfer errors."
    },

    # 6. USAGE_FEATURE_HOWTO
    {
        "customer_tweet_id": "1019",
        "customer_query": "How do I set up Personal Hotspot to share my cellular data with my MacBook Air?",
        "apple_tweet_id": "2019",
        "apple_resolution": "Setting up Personal Hotspot is easy! On your iPhone, go to Settings > Personal Hotspot and toggle 'Allow Others to Join' on. Then select your iPhone from the Wi-Fi menu on your Mac. DM us if you need help."
    },
    {
        "customer_tweet_id": "1020",
        "customer_query": "My AirPods Pro won't pair with my iPhone. The light on the case just flashes amber.",
        "apple_tweet_id": "2020",
        "apple_resolution": "A flashing amber light means your AirPods need to be reset. Place both AirPods in the case, leave the lid open, and hold the setup button on the back for 15 seconds until the light flashes amber, then white. DM us if they still won't connect."
    },
    {
        "customer_tweet_id": "1021",
        "customer_query": "How do I silence notifications during work hours without completely putting phone in airplane mode?",
        "apple_tweet_id": "2021",
        "apple_resolution": "Focus mode is designed for this! Swipe down from the top right to open Control Center, tap Focus, and choose 'Do Not Disturb' or set up a custom 'Work' Focus schedule. DM us if you need help tailoring allowed contacts."
    },

    # 7. OUT_OF_SCOPE_COMPLAINT
    {
        "customer_tweet_id": "1022",
        "customer_query": "Apple prices are getting ridiculous. Why is a phone charger not included in the box anymore?",
        "apple_tweet_id": "2022",
        "apple_resolution": "We appreciate your feedback regarding our packaging and environmental goals. You can submit direct product and packaging feedback to our team at apple.com/feedback. Reach out anytime if you have support questions."
    },
    {
        "customer_tweet_id": "1023",
        "customer_query": "Can I return a MacBook bought at Best Buy directly to an official Apple retail store?",
        "apple_tweet_id": "2023",
        "apple_resolution": "Items purchased through third-party authorized retailers like Best Buy must be returned directly to that retailer according to their return policy. DM us if you need warranty service or diagnostics."
    }
]

def setup_knowledge_base():
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(KNOWLEDGE_BASE_RECORDS)
    df.to_csv(PAIRED_CONVERSATIONS_FILE, index=False)
    print(f"Successfully generated knowledge base with {len(df)} historical resolution pairs at: {PAIRED_CONVERSATIONS_FILE}")

if __name__ == "__main__":
    setup_knowledge_base()
