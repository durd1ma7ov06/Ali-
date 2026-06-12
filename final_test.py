#!/usr/bin/env python3
"""Final comprehensive test for Amir Temur database"""

from knowledge_qa import answer_university_question

tests = [
    ("1. Ismi", "sening isming nima"),
    ("2. Tug'ilgan yili", "qachon va qayerda tug'ilgansiz"),
    ("3. Ota-onasi", "otangiz va onangiz kim bo'lgan"),
    ("4. Poytaxt", "saltanatingiz poytaxti qaysi shahar"),
    ("5. Shior", "shioringiz nima"),
    ("6. Temur Tuzuklari", "temur tuzuklari nima haqida"),
    ("7. Anqara jangi", "anqara jangida kimni mag'lub etgansiz"),
    ("8. Obidalar", "qanday obidalar qurdirgansiz"),
    ("9. Vafoti", "qachon va qayerda vafot etgansiz"),
    ("10. Shaxmat", "shaxmat o'ynashni yaxshi ko'rganmisiz"),
]

print("\n" + "=" * 80)
print("SOHIBQIRON AMIR TEMUR YAKUNIY TESTI")
print("=" * 80 + "\n")

success = 0
total = len(tests)

for name, question in tests:
    result = answer_university_question(question, top_k=10)
    status = "OK" if result['answered'] else "FAIL"
    print(f"{status:4} | {name:25} | {question}")
    if result['answered']:
        success += 1
        answer = result['answer'][:80] + "..." if len(result['answer']) > 80 else result['answer']
        print(f"     | Javob: {answer}")
    print()

print("=" * 80)
print(f"NATIJA: {success}/{total} ({success/total*100:.1f}%)")
print("=" * 80)
