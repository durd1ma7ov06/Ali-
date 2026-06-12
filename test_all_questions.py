#!/usr/bin/env python3
"""
Amir Temur tarixi bo'yicha savollarni test qilish
Test all important questions about Amir Temur
"""

from knowledge_qa import answer_university_question

def test_query(number, question, expected_info=""):
    print("=" * 80)
    print(f"{number}. SAVOL: {question}")
    if expected_info:
        print(f"   Kutilgan ma'lumot: {expected_info}")
    print("=" * 80)
    
    result = answer_university_question(question, top_k=10)
    
    if result['answered']:
        print(f"JAVOB TOPILDI")
        print(f"\n{result['answer']}")
        print(f"\nEngine: {result['engine']}")
        if result['sources']:
            print(f"\nManbalar:")
            for source in result['sources'][:3]:
                print(f"  - {source['title']} (score: {source['score']})")
    else:
        print(f"JAVOB TOPILMADI")
        print(f"Sabab: {result['reason']}")
        if result['sources']:
            print(f"\nQidirilgan manbalar:")
            for source in result['sources'][:3]:
                print(f"  - {source['title']} (score: {source['score']})")
    
    print()
    return result['answered']

def main():
    print("\n" + "=" * 80)
    print("SOHIBQIRON AMIR TEMUR HAQIDA SAVOLLAR TESTI")
    print("=" * 80)
    print()
    
    results = []
    
    # 1. O'zi haqida / ismi
    results.append(test_query(
        1,
        "sening isming nima",
        "Sohibqiron Amir Temur"
    ))
    
    # 2. Tug'ilgan yili va joyi
    results.append(test_query(
        2,
        "qachon va qayerda tug'ilgansiz",
        "1336-yil 9-aprel, Xoja Ilg'or"
    ))
    
    # 3. Ota-onasi
    results.append(test_query(
        3,
        "otangiz va onangiz kim",
        "Amir Tarag'ay va Tegina begim"
    ))
    
    # 4. Poytaxt
    results.append(test_query(
        4,
        "saltanatingiz poytaxti qaysi shahar",
        "Samarqand"
    ))
    
    # 5. Mashhur shior
    results.append(test_query(
        5,
        "shioringiz nima",
        "Kuch adolatdadir"
    ))
    
    # 6. Temur Tuzuklari
    results.append(test_query(
        6,
        "temur tuzuklari nima haqida",
        "Davlat boshqaruvi va qo'shin tartibi"
    ))
    
    # 7. Anqara jangi
    results.append(test_query(
        7,
        "anqara jangida kimni mag'lub etgansiz",
        "Sulton Boyazid I"
    ))
    
    # 8. Qurilgan binolar
    results.append(test_query(
        8,
        "qanday obidalar va binolar qurdirgansiz",
        "Bibixonim, Go'ri Amir, Oqsaroy"
    ))
    
    # 9. Vafoti
    results.append(test_query(
        9,
        "qachon va qayerda vafot etgansiz",
        "1405-yil 18-fevral, O'tror"
    ))
    
    # 10. Shaxmatga qiziqish
    results.append(test_query(
        10,
        "shaxmat o'ynaganmisiz",
        "Shaxmati kabir / katta shaxmat"
    ))
    
    # Natijalar
    print("=" * 80)
    print("TEST NATIJALARI")
    print("=" * 80)
    total = len(results)
    success = sum(results)
    print(f"Jami savollar: {total}")
    print(f"Muvaffaqiyatli: {success}")
    print(f"Muvaffaqiyatsiz: {total - success}")
    print(f"Foiz: {success/total*100:.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    main()
