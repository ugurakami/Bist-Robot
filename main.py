import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import ta
from datetime import datetime, date

# --- AYARLAR ---
# Bu bilgileri GitHub Secrets'tan çekecek, güvenlidir.
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
HESAPLAMALAR_DOSYASI = "haftalik_pozisyonlar.json"

# YENİ KONTROL BAYRAĞI: True yaparsanız BIST100 trendi kırmızıysa AL sinyali gelmez.
# Şimdilik sinyal alabilmek için False yapalım.
CHECK_BIST100 = False

# def pazar_taramasi(): fonksiyonunun içindeki kısım
def pazar_taramasi():
    report = f"📢 *PAZAR HAFTALIK BIST RAPORU* ({date.today().strftime('%d.%m.%Y')})\n\n"
    # ... diğer değişkenler ...

    # BIST100 Kontrol Bayrağı Açık mı?
    if CHECK_BIST100:
        # KODDA SİLECEĞİNİZ BLOK 1: BIST100 Verisini Çekme
        xu100_df = get_weekly_supertrend("XU100")
        if xu100_df is None: 
            send_telegram("❌ HATA: BIST100 verisi çekilemedi.")
            return

        # KODDA SİLECEĞİNİZ BLOK 2: BIST100 Trend Kontrolü
        if xu100_df['Trend'].iloc[-1] != 1:
            send_telegram("⚠️ *BIST100 HAFTALIK TREN DÜŞÜŞTE* → Bu hafta ALIM YOK. Nakitte kalmak mantıklı.")
            save_positions([])
            return

SEKTORLER = {
    # BANKA / FİNANS
    "BANKA": ["AKBNK", "GARAN", "ISCTR", "YKBNK", "HALKB", "TSKB", "VAKBN", "QNBFL"],
    
    # HOLDİNG / SANAYİ ÇEŞİTLİLİĞİ
    "HOLDING": ["KCHOL", "SAHOL", "AEFES", "DOHOL", "AKSA", "ANACM", "KONTR", "ITTFH"],
    
    # GIDA / PERAKENDE / TİCARET
    "PERAKENDE": ["BIMAS", "MGROS", "ULKER", "SOKM", "SASA", "EREGL", "TOASO", "FROTO"],
    
    # HAVACILIK / TURİZM
    "HAVACILIK": ["THYAO", "PGSUS", "TAVHL", "AYDEM", "AYEN"],
    
    # DEMİR-ÇELİK / METAL
    "METAL": ["EREGL", "KRDMD", "ALARK", "CIMSA", "AKSEN", "KCAER", "GOZDE"],
    
    # ENERJİ / PETROL / GAZ
    "ENERJI": ["TUPRS", "ASTOR", "PETKM", "KOZAL", "IPEKE", "GOLTS", "AHLAT", "ENJSA"],
    
    # SAVUNMA / TEKNOLOJİ / YAZILIM
    "TEKNOLOJI": ["ASELS", "VESTL", "ARCLK", "KOZAL", "YEOTK", "MIA", "CWENE", "PENTA", "LOGO"],
    
    # İLETİŞİM / TELEKOM
    "ILETISIM": ["TCELL", "TTKOM", "INFO", "BVSAN"],
    
    # OTOMOTİV / ULAŞIM
    "OTOMOTIV": ["FROTO", "TOASO", "CCOLA", "OTKAR", "JANTS", "TGSAS", "THY"],
    
    # İNŞAAT / ÇİMENTO
    "INSAAT": ["SISE", "ODAS", "HEKTS", "TUMOS", "AKCNS", "CEMAS", "NUHCM"],
    
    # SAĞLIK
    "SAGLIK": ["MPARK", "MEDTR", "DEVA"],

    # DİĞER (Çeşitli)
    "DIGER": ["MAVI", "YATAS", "BIZIM", "OZGYO", "MPARK", "SAFKM"]
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_weekly_supertrend(symbol):
    try:
        df = yf.download(symbol + ".IS", period="2y", interval="1wk", progress=False)
        if len(df) < 50: return None
        
        # SuperTrend Hesapla (Period: 10, Multiplier: 3)
        sti = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        df = df.join(sti)
        
        # Sütun isimlerini düzelt (pandas_ta çıktısına göre)
        st_col = f"SUPERT_10_3.0"
        df['Trend'] = np.where(df['Close'] > df[st_col], 1, -1)
        
        return df
    except:
        return None

def main():
    report = f"📢 *BIST HAFTALIK TARAMA* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
    secilenler = []
    used_sectors = set()

    for sektor, hisseler in SEKTORLER.items():
        if len(used_sectors) >= 3: break # En fazla 3 farklı sektör
        
        for hisse in hisseler:
            if sektor in used_sectors: continue
            
            df = get_weekly_supertrend(hisse)
            if df is None: continue
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # AL SİNYALİ: Trend -1'den 1'e döndüyse (veya Trend 1 ve fiyat desteğe yakınsa)
            # Basitleştirilmiş: Sadece yeni trend başlangıcı veya güçlü trend onayı
            if last['Trend'] == 1:
                # Son mumun kapanışı, SuperTrend desteğinin %10 üzerindeyse (çok uzaklaşmamışsa)
                st_val = last[f"SUPERT_10_3.0"]
                if last['Close'] < st_val * 1.15: 
                    
                    hedef = last['Close'] * 1.15 # %15 Hedef
                    stop = st_val # Stop seviyesi SuperTrend çizgisi
                    
                    secilenler.append(f"✅ *{hisse}* ({sektor})\nFiyat: {last['Close']:.2f} TL\nHedef: {hedef:.2f} TL\nStop: {stop:.2f} TL\n")
                    used_sectors.add(sektor)
                    break # Bu sektörden hisse seçtik, diğer sektöre geç

    if secilenler:
        report += "\n".join(secilenler)
        report += "\n\n⚠️ _Yatırım tavsiyesi değildir. Robotik analiz sonucudur._"
    else:
        report += "Bu hafta uygun kriterde hisse bulunamadı. Nakitte kalmak mantıklı olabilir."

    send_telegram(report)

if __name__ == "__main__":
    main()
