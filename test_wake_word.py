from main import strip_wake_word

test_cases = [
    "sohibqiron sen nechanchi yilda tug'ilgansan",
    "sohibqiron amir temur qachon vafot etgan",
    "amir temur qayerda tug'ilgan",
    "sohipqiron salom",
    "salom amir temur", # should fail because it doesn't start with wake word
    "sohibqiro'n nechanchi yilda tug'ilgansan",
    "Sohibqiron! qachon tug'ilgansiz"
]

print("TESTING WAKE WORD DETECTION:")
print("-" * 60)
for tc in test_cases:
    matched, remaining = strip_wake_word(tc)
    status = "SUCCESS" if matched else "FAILED"
    print(f"Input: {tc!r}")
    print(f"Status: {status}")
    print(f"Remaining: {remaining!r}")
    print("-" * 60)
