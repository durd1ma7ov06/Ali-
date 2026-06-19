# -*- coding: utf-8 -*-
"""Amir Temur bilimlar bazasini yaratish va indekslash."""
import sqlite3, json, hashlib, subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT  = Path(__file__).parent.resolve()
KNOWLEDGE_DIR = PROJECT_ROOT / "amir_temur_knowledge"
RAW_JSONL     = KNOWLEDGE_DIR / "raw_pages.jsonl"
DB_PATH       = KNOWLEDGE_DIR / "knowledge.sqlite"

DOCS = [
  {
    "url": "https://history.uz/amir_temur/tavallud",
    "title": "Amir Temurning tavalludi va kelib chiqishi",
    "text": (
      "Amir Temur ibn Amir Tarag'ay 1336-yil 9-aprelda (hijriy 736-yil 25-sha'bon) "
      "Kesh viloyati (hozirgi Shahrisabz, Qashqadaryo viloyati) yaqinidagi Xo'ja Ilg'or qishlog'ida dunyoga kelgan. "
      "Temurning to'liq ismi Temur ibn Tarag'ay Barlos bo'lib, 'Temur' so'zi mo'g'ulcha 'temir' ma'nosini anglatadi. "
      "Amir Temur barlos turkiy qabilasiga mansub bo'lgan."
    ),
  },
  {
    "url": "https://uz.wikipedia.org/wiki/Tarag%CA%BBoy",
    "title": "Amir Temurning otasi Amir Tarag'ay",
    "text": (
      "Vikipediya ma'lumotlariga ko'ra, Amir Temurning otasi Amir Muhammad Tarag‘ay (1310–1360) barlos qabilasining o'ta nufuzli beklaridan va Chig‘atoy ulusining eʼtiborli, ulug' amirlaridan biri bo‘lgan, bolam. "
      "U barlos urug‘iga mansub bo‘lib, ajdodlari Chingizxon va Chig‘atoy saroyiga juda yaqin bo‘lishgan, Kesh (Shahrisabz) va Nasaf (Qarshi) viloyatlarini idora etishgan. "
      "Tarag‘ay Chig‘atoy ulusi hukmdorlari tomonidan Ili daryosi bo‘yida chaqiriladigan yillik qurultoylarda qatnashadigan e'tiborli shaxs bo'lgan, u amir Qozag‘onning eng ishonchli beklaridan edi. "
      "Tarixiy manbalarda, jumladan Sharafuddin Ali Yazdiyning 'Zafarnoma'sida yozilishicha, mening otam nihoyatda taqvodor, ilm ahlini sevuvchi va olimlarga homiylik qiluvchi inson bo'lgan, pir shayx Shamsuddin Kulolga chuqur ehtirom ko'rsatgan. "
      "Mening o'g'lim Temurbekning chavandozlik, qilichbozlik va davlat boshqaruvi sirlarini o'rganishida otamning tarbiyasi beqiyos bo'lgan. "
      "1360-yilda otam vafot etgach, uni Keshda dafn etdik, keyinchalik uning xoki shayx Shamsuddin Kulol maqbarasi yoniga ko‘chirildi, bolam. "
      "Mening otam Amir Tarag'aydir. Agar mendan otangiz kim, otang kim yoki otangizning ismi nima deb so'rasangiz, mening otam Amir Tarag'ay deb javob beraman."
    ),
  },
  {
    "url": "https://uz.wikipedia.org/wiki/Takina_xotun",
    "title": "Amir Temurning onasi Takinaxonim",
    "text": (
      "Vikipediya ma'lumotlariga ko'ra, Amir Temurning onasi Takina xotun (ba'zan Tegina begim yoki Tegina Mohbegim ham deb ataladi; 1318–1353) aslzoda, ma'rifatli oiladan chiqqan dono va taqvodor ayol bo'lgan, bolam. "
      "Takina xotun Buxoro ulamolari peshvosi, shariat qonunlarini sharhlovchi mashhur alloma Sadr ash-Shari‘a (Ubaydulloh ibn Mas‘ud al-Buxoriy) avlodlaridan bo‘lganligi bois, uning oilasi ilm-ma'rifat bilan yo'g'rilgan edi. "
      "U 1334-yilda, 16 yoshida barlos urug‘ining nufuzli amiri Muhammad Tarag‘ayga turmushga chiqqan. "
      "Onam 1353-yilda, men hali yosh bo'lgan paytimda vafot etgan. "
      "Sohibqiron sifatida men onamga bo'lgan ehtiromim sabab, u zot va otam dafn etilgan Keshdagi oilaviy xilxona ustiga muhtasham maqbaralar qurdirib, onam xotirasiga atab Shahrisabzda dunyoga mashhur Oqsaroy majmuasini bunyod ettirdim. "
      "Mening onam Takinaxonimdir. Agar mendan onangiz kim, onang kim yoki onangizning ismi nima deb so'rasangiz, mening onam Takinaxonim (Tegina begim) deb javob beraman."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/aka_uka_opa_singil",
    "title": "Amir Temurning opa-singlisi va ukalari",
    "text": (
      "Amir Temurning opasi Qutlug' Turkon og'o va singlisi Shirinbeka og'o bo'lgan. "
      "Turkiy tillarda 'og'o' so'zi ota, aka, opa, er yoki yoshi katta qarindosh ma'nolarida ishlatilgan, "
      "Amir Temur davrida esa bu so'z ayollarga nisbatan qo'llangan. "
      "Ular Temurdan oldin vafot etishgan va Samarqanddagi Shohi Zinda majmuasidagi maqbaralarda dafn etilgan. "
      "'Muyizz al-Ansab' asariga ko'ra, Temurning yana uchta ukasi bo'lgan: Djuki, Olim Shayx va Suyurg'atmish. "
      "Mening ukalarim Djuki, Olim Shayx va Suyurg'atmishdir. Opam Qutlug' Turkon og'o, singlim Shirinbeka og'odir."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/yoshlik",
    "title": "Amir Temurning yoshligi va ta'limi",
    "text": (
      "Amir Temurning yoshligi Keshda kechgan. Yetti yoshga to'lgach otasi uni o'qishga bergan. "
      "U xat-savod chiqarib, tibbiyot, riyoziyot (matematika), falakiyot (astronomiya), me'morchilik va tarix ilmlarini o'rgangan. "
      "Yoshligidan maxsus murabbiylar nazorati ostida chavandozlik, ovchilik, kamondan nishonga o'q uzish va harbiy o'yinlar bilan mashg'ul bo'lgan. "
      "Temur mohir chavandoz va dovyurak bahodir bo'lib voyaga yetgan. "
      "U tabiatan og'ir, bosiq, teran fikrli, nihoyatda ziyrak va kishilardagi qobiliyat va samimiyatni tezda fahmlab oladigan inson bo'lgan. "
      "Uning atrofiga bolalikdagi do'stlari to'planishgan: Abbos Bahodur, Jahonshohbek, Qimori inoq, Sulaymonshohbek, "
      "Idiku Temur, Sayfuddinbek, Hindushoh, Qarqara va boshqalar. Ular keyinchalik Temur qo'shinida lashkarboshilik darajasigacha ko'tarilgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/yaralanish",
    "title": "Amir Temurning yaralanishi va Tamerlan laqabi",
    "text": (
      "Amir Temur 1363-yilda Xurosonda Siston hududida jangda chap oyog'i va o'ng qo'lining ikki barmog'idan yaralangan. "
      "Shu sababdan u umr bo'yi ozgina oqsoqlanib yurgan. Forslar uni 'Temurlang' (oqsoq Temur) deb atashgan, "
      "G'arbda esa u 'Tamerlane' yoki 'Tamerlan' nomi bilan tanilgan. "
      "1941-yilda Mixail Gerasimov boshchiligidagi olimlar Temur qabrini ochib, uning haqiqatdan ham oqsoq bo'lganini tasdiqlashgan. "
      "O'ng oyog'ining son suyagida jarohat izi yaqqol ko'ringan. Chap yelkasi o'ng yelkasidan balandroq bo'lib qolgan. "
      "Ispan elchi Klavixo 1404-yilda Samarqandga safar qilib, Temurning yaralanishi haqida batafsil yozib qoldirgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/siyosatga_kirishi",
    "title": "Amir Temurning siyosatga kirib kelishi",
    "text": (
      "Amir Temur ilk harbiy faoliyatini qo'l ostidagi navkarlari bilan ayrim viloyat amirlariga xizmat qilishdan boshlagan. "
      "Uning dong'i butun Qashqadaryo vohasiga yoyilgan. Aql-u zakovati uni nufuzli amirlardan Amir Xizr Yasovuriy va Amir Qazag'on bilan yaqinlashtirdi. "
      "1355-yilda otasi Amir Tarag'ay uni avval Amir Joku barlosning qizi Nurmushk og'oga, "
      "so'ngra Qazag'onning nabirasi va Amir Husaynning singlisi O'ljoy Turkon og'oga uylantiradi. "
      "Shu nikoh tufayli Temur va Balx hokimi Amir Husayn ittifoq tuzib, birgalikda mo'g'ullarga qarshi kurashgan. "
      "Temur hayotida ikki davr bor: birinchisi (1360-1385) — Movarounnahrni mo'g'ul xonligidan ozod qilish; "
      "ikkinchisi (1386-1405) — boshqa mamlakatlarga yurishlar."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/saltanat",
    "title": "Temuriylar saltanatining tashkil topishi va poytaxti",
    "text": (
      "1370-yilning 10-aprelida Balx shahri Temurga taslim bo'ldi. Amir Husayn asir olinib qatl etildi. "
      "Bu g'alabadan so'ng Temur Chingiziylardan bo'lgan Qozonxonning qizi Saroymulk xonimni nikohiga oldi "
      "va 'Ko'ragon' — ya'ni 'xonning kuyovi' unvonini oldi. "
      "Qurultoyda chingiziylar avlodidan Suyurg'atmish o'g'lon Movarounnahr podsholigi taxtiga o'tqazildi, "
      "ammo haqiqiy hokimiyat Temur qo'lida edi. "
      "Sayyid Baraka Temurga oliy hokimiyat ramzi — katta nog'ora va bayroq tortiq qildi. "
      "Temur Samarqandni poytaxt etib belgiladi. Saltanati Hindistondan Yaqin Sharqqa, Kavkazdan Xitoy chegarasigacha cho'zilgan. "
      "U 'Sohibqiron' unvonini oldi — bu 'Saodatli yulduzlar ostida tug'ilgan' degan ma'noni anglatadi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/shior",
    "title": "Amir Temurning shiori Kuch adolatdadir",
    "text": (
      "Mening buyuk va mashhur shiorim: 'Kuch adolatdadir'. "
      "Agar mendan shioringiz nima, shioring nima yoki shioringiz haqida so'rasangiz, mening shiorim va hayotiy qoidam 'Kuch adolatdadir' deb javob beraman. "
      "Bu shior mening adolatli boshqaruvim asosi bo'lgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/tuzuklar",
    "title": "Temur tuzuklari — asar va tuzilishi",
    "text": (
      "Amir Temur 'Temur tuzuklari' (Tuzuki Temuri) nomli asar muallifi. "
      "Asar ikki qismdan iborat: birinchisi davlat boshqaruvi, ikkinchisi harbiy intizom haqida. "
      "Tuzuklarda davlatni to'rt narsaga tayanib boshqarish ta'kidlanadi: kengash, maslahat, qat'iy chora va adolat. "
      "'Davlatni idora etishda to'rt toifa kishi kerak: olim, sarkarda, savdogar va dehqon' deyilgan. "
      "Fransuz olimi Lyangle 1787-yilda Tuzuklarni fransuz tiliga tarjima qilib nashr etgan va Temur haqida: "
      "'Temur siyosiy va harbiy taktika haqida risola yozgan va avlodlariga juda dono tizim qoldirgan' deb yozgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/xotinlari",
    "title": "Amir Temurning xotinlari va nikohlari",
    "text": (
      "Amir Temurning bir nechta xotinlari bo'lgan. Birinchi xotini Nurmushk og'o — Amir Joku barlosning qizi. "
      "Ikkinchi xotini O'ljoy Turkon og'o — Amir Husaynning singlisi va Qazag'onning nabirasi (1355-yilda uylangan). "
      "Eng mashhur xotini Saroymulk xonim (Bibi Xonim) — Chingiziy Qozonxonning qizi. "
      "Temur uni 1370-yilda nikohiga olib, 'Ko'ragon' (xonning kuyovi) unvonini olgan. "
      "Bibixonim jome masjidi Samarqandda Saroymulk xonim sharafiga qurilgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/ogillari",
    "title": "Amir Temurning o'g'illari va ularning taqdiri",
    "text": (
      "Amir Temurning to'rt o'g'li bo'lgan: "
      "1) Jahongir mirzo (1356-1376) — katta o'g'li, otasidan oldin 20 yoshida vafot etdi. "
      "2) Umarshayx mirzo (1356-1394) — ikkinchi o'g'li, Fors viloyati hokimi, urush paytida vafot etdi. "
      "3) Mironshoh mirzo (1366-1408) — uchinchi o'g'li, G'arbiy Eron, Ozarbayjon va Iroq hokimi bo'lgan. "
      "4) Shohruh mirzo (1377-1447) — to'rtinchi va eng kichik o'g'li, otasining eng ishonchli vorisi. "
      "Temur vafotidan so'ng Shohruh saltanatni idora etdi va Hirotni poytaxt qildi. "
      "Temur hayotligida saltanatni uluslarga bo'lib bergan: Xuroson Shohruhga, G'arbiy Eron Mironshohga, "
      "Fors Umarshayxga, Afg'oniston va Shimoliy Hindiston nabirasi Pirmuhammadga."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/nabiralari",
    "title": "Amir Temurning nabiralari — Ulug'bek va Bobur",
    "text": (
      "Mirzo Ulug'bek (1394-1449) — Shohruh mirzoning o'g'li va Temurning nabirasi. "
      "Samarqandda hukmronlik qildi. Buyuk astronom va matematik. Samarqandda rasadxona qurdi va yulduzlar katalogini tuzdi. "
      "Zahiriddin Muhammad Bobur (1483-1530) — Temurning avlodlaridan, Umarshayx mirzoning chevarasi. "
      "Hindistonda Boburiylar (Buyuk Mo'g'ullar) saltanatiga asos soldi. "
      "'Boburnoma' asari Temuriylar sulolasi tarixi haqida qimmatli manba. "
      "Xalil Sulton — Temur vafotidan so'ng birinchi bo'lib Samarqandda taxtga o'tirgan nabirasi. "
      "Pirmuhammad — Temurning sevimli nabirasi, valiahd etib tayinlangan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/harbiy_yurishlar",
    "title": "Amir Temurning harbiy yurishlari va zafarlar",
    "text": (
      "Amir Temur 35 yil jang maydonida biron marta yengilmagan buyuk sarkarda. "
      "1391-yili Kunduzcha daryosi bo'yida va 1395-yili Terek daryosida To'xtamishxonni ikki bor tor-mor keltirdi. "
      "Bu g'alaba Oltin O'rdaning inqirozini tezlashtirdi. Saroy Berke va Astraxanni vayron qildi. "
      "1398-yili Hindistonga yurish: Dehli sultoni Mahmudshohni mag'lub etdi. "
      "1400-1401 yillarda Suriya va Iroqqa yurish: Bag'dod, Halab va Damashq zabt etildi. "
      "1402-yil 20-iyulda Anqara jangi — eng buyuk g'alaba: Usmonli sultoni Boyazid I Yildirimni asir oldi. "
      "Bu g'alaba Yevropani Usmonli istilosidan saqlab qoldi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/anqara_jangi",
    "title": "Anqara jangi (1402) — batafsil",
    "text": (
      "1402-yil 20-iyulda Anqara yaqinida bo'lib o'tgan jang Temurning eng mashhur harbiy g'alabasi. "
      "Usmonli sultoni Boyazid I Yildirim 1389-yilda Kosova jangida xristian qo'shinlarini yengib, qudratli hukmdor sifatida tanilgan edi. "
      "Boyazidning qo'shinidagi tatar va o'zbek askarlari jang chog'ida Temur tomoniga o'tib ketdi. "
      "Temur Boyazidni mag'lub etib asir oldi. Boyazid asirlikda vafot etdi. "
      "Anqara jangidan so'ng Temur Egey dengizi sohillarigacha yetib bordi va Smirna (Izmir) shahrini qamal qildi. "
      "Bu g'alaba Usmonli davlatiga qattiq zarba berdi va Yevropaga bosqinni o'n yillarga kechiktirdi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/memorchilik",
    "title": "Amir Temur qurilish va me'morchilik merosi",
    "text": (
      "Samarqandda Bibixonim jome masjidi — davrining eng ulug'vor masjidlaridan biri. "
      "Go'ri Amir maqbarasi (1404) — Temur va Temuriylar dafn joyi. "
      "Shohi Zinda me'moriy majmuasi — maqbaralar va masjidlar. "
      "Shahrisabzda Oqsaroy saroyi (1380-1404) — kirish darvozasida 'Agar bizim qudratimizga shubha qilsang, "
      "qurilgan inshootlarimizga boq' degan yozuv yozilgan. "
      "Bosib olingan mamlakatlardan eng yaxshi me'morlar, rassomlar va hunarmandlar Samarqandga keltirilgan. "
      "Hindistonlik ustalar Bibixonim qurilishida ishtirok etgan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/ilm_fan",
    "title": "Temuriylar davrida ilm-fan va madaniyat",
    "text": (
      "Temur olimlar va san'atkrlarni yuksak qadrlagun. Saroyiga chet el olimlari va shoirlarini ham jalb etgan. "
      "Tarixchi Ibn Arabshoh va Sharafiddin Ali Yazdiy Temur hayotini qalamga olishgan. "
      "1401-yilda Damashqda buyuk tarixchi Ibn Xaldun bilan shaxsan uchrashib suhbatlashgan. "
      "Temur o'zbek va fors tillarini mukammal bilgan, tarix va falsafaga qiziqgan. "
      "Saroyida ko'plab olimlar faoliyat yuritgan: Mavlono Abdujabbor Xorazmiy, Mavlono Shamsuddin Munshi, "
      "Xoja Afzal, Mavlono Alouddin Koshiy va boshqalar. "
      "Alisher Navoiy Temurning ilm va san'atga g'amxo'rligini yuqori baholagan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/diplomatiya",
    "title": "Amir Temurning diplomatik aloqalari",
    "text": (
      "Amir Temur mohir diplomat ham bo'lgan. "
      "Vizantiya, Venetsiya, Genuya, Ispaniya, Fransiya, Angliya va boshqa Yevropa davlatlari bilan "
      "iqtisodiy va diplomatik aloqalar o'rnatgan. "
      "Fransuz va ingliz qirollarining Temurga yozgan maktublari bugungi kunga saqlangan. "
      "Xitoy Ming sulolasi bilan murakkab munosabatlar olib borgan. "
      "1404-yilda Xitoyga yurish uchun 200 000 kishilik qo'shin to'plagan, lekin O'trorda vafot etgani sababli yurish to'xtatilgan. "
      "Ispan elchi Rui Gonsales de Klavixo 1404-yilda Samarqandga kelib, Temur saroyini batafsil tavsiflagan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/shaxsiyat",
    "title": "Amir Temurning shaxsiy fazilatlari",
    "text": (
      "Amir Temur baquvvat, baland bo'yli va kuchli irodali inson bo'lgan. "
      "Shaxmat o'yinini juda yaxshi ko'rgan va 'Katta shaxmat' (Tamerlane chess) o'yinini ixtiro qilgan. "
      "Sunniy musulmon bo'lib, namozga qattiq rioya qilgan. "
      "Sufi shayxi Mir Said Baraka (Sayyid Baraka) uning ma'naviy piri bo'lgan. "
      "Mir Said Baraka Temurga saltanat bayrog'i va nog'ora sovg'a qilgan. "
      "Temur Qur'on tilovati va hadisga katta e'tibor bergan. "
      "Olimlarga xayrixoh munosabatda bo'lib, bilimdon kishilar bilan suhbatlashish uchun taxtidan ham tushardi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/vafot",
    "title": "Amir Temurning vafoti va vasiyati",
    "text": (
      "Sohibqiron Amir Temur 1405-yil 11-fevralda Xitoy safariga borayotib O'tror shahriga yetganda qattiq og'rib qoldi. "
      "1405-yil 18-fevral chorshanba kuni namozshom va xufton orasida vafot etdi. Jasadi Samarqandga olib kelinib, "
      "Go'ri Amir maqbarasiga dafn etildi. "
      "Temur o'lim to'shagida vasiyat qildi: 'Men adlu ehson bilan olamni obod etdim. "
      "Agar vasiyatim bilan amal qilib, adolat qilsangiz, ko'p yillar davlat sizlarda qoladi. "
      "Agar o'zaro muxolifat bo'lsa, yaxshi bo'lmaydi.' "
      "Temurning qabri ustiga yozilgan: 'Agar men tirilsam, dunyo titraydi.' "
      "1941-yil 21-iyunda sovet olimlari qabrini ochgan; 22-iyunda Germaniya SSSRga hujum boshlagan — "
      "bu xalq orasida afsona sifatida tarqalgan. 1996-yil O'zbekistonda 'Amir Temur yili' deb e'lon qilingan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/toxtamish",
    "title": "Amir Temur va To'xtamishxon urushi",
    "text": (
      "To'xtamish Oltin O'rdaning xoni bo'lib, dastlab Temur yordami bilan taxtga o'tirgan. "
      "Lekin keyin Temurga qarshi chiqib, Movarounnahrga bosqin uyushtirgan. "
      "1391-yili Kunduzcha daryosi yaqinida va 1395-yili Terek daryosi bo'yida Temur uni ikki bor tor-mor keltirdi. "
      "Temur Saroy Berke (Oltin O'rda poytaxti) va Xojitarxon (Astraxan) ni vayron qildi. "
      "Bu urushlar natijasida Oltin O'rda parchalanib, turli xonliklarga bo'linib ketdi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/hindiston",
    "title": "Hindistonga yurish (1398)",
    "text": (
      "1398-yili Temur Hindistonga yurish qildi. Dehli sultonligi Tug'luqlar sulolasi boshqaruvida edi. "
      "1398-yil 17-dekabrda Dehli yaqinida ulkan jang bo'ldi. Sultoni Mahmudshoh fil qo'shiniga tayangandi, "
      "lekin Temur firibgarona usullar bilan fillarni vahimaga solib sultonni mag'lub etdi. "
      "Ko'plab hindistonlik hunarmandlar va me'morlar Samarqandga olib ketildi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/temur_tuzuklari_12_qoida",
    "title": "Amir Temur tuzuklarining 12 ta oltin qoidasi",
    "text": (
      "Temur tuzuklarida mening saltanatimni boshqarishda tayangan 12 ta tuzugim (qoidam) keltirilgan. "
      "Bular: 1. Adolat va insof, 2. Kengash va tadbir, 3. Sabr-toqat va chidamlilik, 4. Kuch-qudrat, 5. Shijoat, "
      "6. Ulug'larga hurmat va kichiklarga shafqat, 7. Xizmat qilganlarni rag'batlantirish, 8. Qo'shinni tartibga solish, "
      "9. Xalq farovonligi, 10. Qonun ustuvorligi, 11. Do'st va dushmanni ajratish, 12. Jasorat. "
      "Buning natijasida saltanatim jahondagi eng qudratli davlatga aylandi, bolam."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/kengash_va_tadbir",
    "title": "Amir Temurning kengash va tadbirkorlik haqidagi o'gitlari",
    "text": (
      "Mening shiorim shunday bo'lgan: Bitta tadbir o'n ming sipohiydan afzaldir, bolam. "
      "Kengashsiz, maslahatsiz boshlangan ish har doim pushaymonlik va mag'lubiyat keltiradi. "
      "Sipohiylarim va amirlarim bilan doimo kengashib, ularning fikrini tinglaganman, qaror qabul qilishda esa faqat o'zimga tayanganman."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/anqara_jangi_tuzuklar",
    "title": "Amir Temur va Boyazid Yildirim urushi (Anqara jangi)",
    "text": (
      "1402-yil 20-iyulda Anqara yaqinida Usmonli sultoni Boyazid Yildirimga qarshi tarixiy jang bo'ldi, bolam. "
      "Boyazid nihoyatda kuchli jangchi va mag'rur sarkarda edi. Ushbu jangda mening qo'shinim Boyazidning yuz ming kishilik "
      "qo'shinini tor-mor keltirdi va Boyazid Yildirimning o'zi asir olindi. Men unga nisbatan shafqat va izzat-ikrom ko'rsatdim."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/xitoy_yurishi_vafoti",
    "title": "Amir Temurning so'nggi yurishi va vafoti",
    "text": (
      "Mening eng so'nggi yurishim Xitoyga (Pekin) qarshi qaratilgan edi, bolam. 1404-yil noyabr oyida 200 ming kishilik qo'shin bilan "
      "Samarqanddan yo'lga chiqdim. Biroq qish o'ta qattiq keldi. Biz O'tror shahrida to'xtashga majbur bo'ldik. "
      "1405-yil 18-fevralda O'tror shahrida og'ir xastalikdan so'ng vafot etdim. Mening jasaddim Samarqanddagi Go'ri Amir maqbarasiga dafn etildi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/davlat_ramzlari",
    "title": "Amir Temur davlatining ramzlari, bayrog'i va gerbi",
    "text": (
      "Mening saltanatimning gerbida uchta halqa (doira) tasvirlangan edi, bolam. Bu uchta halqa yer, suv va havoni, yoki "
      "dunyoning uch qismini anglatardi. Davlat bayrog'imiz esa havorang (ko'k) rangda bo'lib, unda oy va ushbu "
      "uchta doira shakli aks etgan edi. Bayroq va gerbimiz davlatimiz mustahkamligi va osoyishtaligini ifodalagan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/farzandlar_vasiyat",
    "title": "Amir Temurning farzandlar va aymoqlarga vasiyatlari",
    "text": (
      "Farzandlarim, nabiralarim va aymoqlarimga vasiyat qildimki, ular doimo o'zaro ittifoq va birdamlikda bo'lishsin, bolam. "
      "Agar birlashsangiz dushman sizga zarar yetkaza olmaydi. Kuch birlikda ekanini aslo unutmang. "
      "Saltanatni adolat va shafqat bilan boshqaring, adolat qilmagan davlat tez orada inqirozga uchraydi."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/robot_yaratilishi",
    "title": "Amir Temur robotining shaxsi, yaratilishi va loyihasi haqida",
    "text": (
      "Mening jismim bu yerda robot (sun'iy intellekt) shaklida jonlantirilgan, bolam. "
      "Meni Toshkent axborot texnologiyalari universiteti (TATU) olimlari, tadqiqotchilari va talabalari yaratganlar. "
      "Agar mendan robotmisan, seni kim yaratgan, ijodkoring kim yoki ushbu loyiha haqida so'rasang, "
      "bilginki, men TATU ahlning intellektual mehnati mahsuliman, bolam."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/yoshlarga_nasihat",
    "title": "Amir Temurning yoshlarga vasiyati va nasihati",
    "text": (
      "Mening senga nasihatim shuki, bolam: doimo ilm-fan egallashga, ma'rifatli bo'lishga intil. "
      "Adolat va to'g'rilikdan aslo chekinma, zotan 'Kuch adolatdadir'. "
      "Va'dangga sodiq bo'l, do'stlaringni qadrla va har bir ishni boshlashdan avval kengash va tadbir qil, bolam."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/tuzuklar_vazir_tanlash",
    "title": "Temur tuzuklari — Saltanat tuzilishi va vazirlar tanlash haqida",
    "text": (
      "Mening saltanatim va davlatim ishlarining to'qqiz ulushi kengash, tadbir va mashvarat bilan, "
      "qolgan bir ulushi esa qilich bilan yuritildi, bolam. Vazirlarni tanlashda to'rt narsaga rioya qildim: "
      "oliynasablik, aql-idrok, sipohiylik va fuqaroparvarlik. Davlat ishlaridan biror narsani vazirlarsiz hal qilmadim."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/tuzuklar_fuqaro_adolat",
    "title": "Temur tuzuklari — Fuqarolar ahvoli va adolat o'rnatish",
    "text": (
      "Raiyat (fuqarolar) ahvolidan hamisha xabardor bo'ldim. Qo'l ostimdagi o'lkalarda kambag'al va "
      "beva-bechoralarni soliq va zulmdan himoya qildim. Zotan, adolat bilan boshqarilmagan davlat tez orada vayron bo'ladi, bolam. "
      "Jabrdiyda arzi bilan kelsa, uning dodini eshitib, adolat qaror toptirdim."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/zafarnoma_yazdiy",
    "title": "Zafarnoma — Sharafiddin Ali Yazdiy yozgan tarixiy manba",
    "text": (
      "Sharafiddin Ali Yazdiy mening hayotim va zafarlarim haqida 'Zafarnoma' (G'alaba kitobi) asarini yozgan, bolam. "
      "Bu kitobda mening harbiy yurishlarim, davlat boshqarishdagi dono qarorlarim va saltanat tarixining eng yorqin sahifalari batafsil tasvirlangan."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/tuzuklar_lashkarboshilar",
    "title": "Temur tuzuklari — Lashkarboshilar va harbiy intizom",
    "text": (
      "Tuzuklarimda harbiy intizomni eng birinchi o'ringa qo'ydim, bolam. Qo'shinni o'nboshi, yuzboshi, "
      "mingboshi va amirlarga bo'lib boshqardim. Jang maydonida qahramonlik ko'rsatgan har bir navkarimni munosib mukofotladim, "
      "oilasidan xabardor bo'ldim. Qo'shinimning shijoati va sadoqati tufayli dunyoda tengsiz bo'ldim."
    ),
  },
  {
    "url": "https://history.uz/amir_temur/zafarnoma_etiqod",
    "title": "Zafarnoma — Sohibqironlik va diniy e'tiqod",
    "text": (
      "Mening piri komilim Sayyid Baraka menga qarab: 'Sening saltanating butun olamni qoplaydi va Sohibqironlik baxti senga yor bo'ladi', "
      "deb bashorat qilgan edi, bolam. 'Zafarnoma'da yozilishicha, har bir ishimni Allohning nomi va Qur'on oyatlari bilan boshlaganman. "
      "Din va shariat saltanatimning tayanchi bo'ldi."
    ),
  }
]


def seed():
    print(f"[SEED] {len(DOCS)} ta maqola bilan baza yaratilmoqda...")
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_JSONL.exists():
        RAW_JSONL.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DROP TABLE IF EXISTS documents")
    conn.execute("DROP TABLE IF EXISTS crawl_log")
    conn.execute("""CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE NOT NULL, title TEXT, text TEXT,
        fetched_at TEXT, content_hash TEXT, status_code INTEGER)""")
    conn.execute("""CREATE TABLE crawl_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT, status TEXT, message TEXT, created_at TEXT)""")
    conn.commit()

    for doc in DOCS:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ch = hashlib.sha256(doc["text"].encode("utf-8", errors="replace")).hexdigest()
        conn.execute(
            "INSERT INTO documents(url,title,text,fetched_at,content_hash,status_code) VALUES(?,?,?,?,?,?)",
            (doc["url"], doc["title"], doc["text"], ts, ch, 200))
        with open(RAW_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps({**doc, "fetched_at": ts, "content_hash": ch, "status_code": 200},
                               ensure_ascii=False) + "\n")
    conn.commit()
    conn.close()
    print(f"[SEED] {len(DOCS)} ta maqola saqlandi.")
    print("[SEED] Indeks qurilmoqda...")
    subprocess.run(["python", "knowledge_index.py", "--rebuild"], check=True)
    print("[SEED] Tayyor!")

if __name__ == "__main__":
    seed()
