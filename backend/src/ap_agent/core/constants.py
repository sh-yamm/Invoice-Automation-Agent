"""Fixed facts about the buying company and India."""

BUYER_NAME = "Sample Client Retail Pvt Ltd (demo company)"  # a made-up demo company
BUYER_STATE = "29"
BUYER_ADDRESS = "No. 14, Outer Ring Road, Bellandur, Bengaluru 560103, Karnataka"
# Base 29AABCZ5821K1Z + mod-36 check digit "W" (verified in tests/unit/rules/test_india.py).
BUYER_GSTIN = "29AABCZ5821K1ZW"

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}

OUTCOME_LABELS = {0: "Approved", 1: "Needs sign-off", 2: "On hold", 3: "Rejected"}
