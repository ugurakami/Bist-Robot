import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import ta # Yeni kütüphanemiz
from datetime import datetime, date

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
HESAPLAMALAR_DOSYASI = "haftalik_pozisyonlar.json"
CHECK_BIST100 = False # Piyasadan bağımsız sinyal için False

# ====================== GENİŞLETİLMİŞ VE NİHAİ SEKTÖR LİSTESİ ======================
SEKTORLER = {
    "BANKA": ["AKBNK", "GARAN", "ISCTR", "YKBNK", "HALKB", "TSKB", "VAKBN", "QNBFL"],
    "HOLDING": ["KCHOL", "SAHOL", "AEFES", "DOHOL", "AKSA", "ANACM", "KONTR", "ITTFH"],
    "PERAKENDE": ["BIMAS", "MGROS", "ULKER", "SOKM", "SASA", "EREGL", "TOASO", "FROTO"],
    "HAVACILIK": ["THYAO", "PGSUS", "TAVHL", "AYDEM", "AYEN"],
    "METAL": ["EREGL", "KRDMD", "ALARK", "CIMSA", "AKSEN", "KCAER", "GOZDE"],
    "ENERJI": ["TUPRS", "ASTOR", "PETKM", "KOZAL", "IPEKE", "GOLTS", "AHLAT", "ENJSA"],
    "TEKNOLOJI": ["ASELS", "VESTL", "ARCLK", "KOZAL", "YEOTK", "MIA", "CWENE", "PENTA", "LOGO"],
    "ILETISIM": ["TCELL", "TTKOM", "INFO", "BVSAN"],
    "OTOMOTIV": ["FROTO", "TOASO", "CCOLA", "OTKAR", "JANTS", "TGSAS", "THY"],
    "INSAAT": ["SISE", "ODAS", "HEKTS", "TUMOS", "AKCNS", "CEMAS", "NUHCM"],
    "SAGLIK": ["MPARK", "MEDTR", "DEVA"],
    "DIGER": ["MAVI", "YATAS", "BIZIM", "OZGYO", "MPARK", "SAFKM"]
}

# --- YARDIMCI FONKSİYONLAR ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def save_positions(positions):
    """Bulunan hisseleri sonraki kontrol için kaydeder."""
    with open(HESAPLAMALAR_DOSYASI, 'w') as f:
        json.dump(positions, f)

def load_positions():
    """Kaydedilmiş hisseleri yükler."""
    if os.path.exists(HESAPLAMALAR_DOSYASI):
        with open(HESAPLAMALAR_DOSYASI, 'r') as f:
            return json.load(f)
    return []

# --- SUPER TREND HESAPLAMA (ta KÜTÜPHANESİ İLE DÜZELTİLDİ) ---
def get_weekly_supertrend(symbol):
    try:
        df = yf.download(symbol + ".IS", period="2y", interval="1wk", progress=False)
        if len(df) < 50: return None
        
        # ta.trend.supertrend ile hesaplama (Period=10, Multiplier=3.0)
        st_data = ta.trend.supertrend(
            close=df['Close'], 
            high=df['High'], 
            low=df['Low'], 
            window=10, 
            coefficient=3.0
        )
        
        # Sütun adları ta kütüphanesine göre düzeltildi
        df = df.join(st_data)
        
        # SUPERT_D_10_3.0, SuperTrend çizgisinin değeridir.
        df['ST_Value'] = df['SUPERT_D_10_3.0'] 
        
        # SUPERT_10_3.0 > 0 ise yukarı trend, < 0 ise aşağı trend
        df['Trend'] = np.where(df['SUPERT_10_3.0'] > 0, 1, -1) 
        
        return df.dropna()

    except Exception as e:
        print(f"Veri çekme veya SuperTrend hesaplamasında hata oluştu: {e}")
        return None

# --- PAZAR TARAMASI (AL SİNYALİ) ---
def pazar_taramasi():
    report = f"📢 *PAZAR HAFTALIK BIST RAPORU* ({date.today().strftime('%d.%m.%Y')})\n\n"
    secilenler = []
    used_sectors = set()
    positions_to_save = []

    # BIST100 Kontrolü (Bayrak ile yönetiliyor)
    if CHECK_BIST100:
        xu100_df = get_weekly_supertrend("XU100")
        if xu100_df is None or xu100_df['Trend'].iloc[-1] != 1:
            send_telegram("⚠️ *BIST100 HAFTALIK TREN DÜŞÜŞTE* → Bu hafta ALIM YOK. Nakitte kalmak mantıklı.")
            save_positions([])
            return

    for sektor, hisseler in SEKTORLER.items():
        if len(used_sectors) >= 3: break # En fazla 3 farklı sektör
        
        for hisse in hisseler:
            if sektor in used_sectors: continue
            
            df = get_weekly_supertrend(hisse)
            if df is None: continue
            
            last = df.iloc[-1]
            st_val = last['ST_Value']
            
            # YENİ DÜŞÜK RİSKLİ GİRİŞ KOŞULU (Pullback mantığı)
            # Trend yukarı (1) OLMALI ve Fiyat SuperTrend çizgisinden %15'ten fazla uzaklaşmamalı.
            if last['Trend'] == 1 and last['Close'] < st_val * 1.15: 
                
                # Minimum hacim, fiyat ve beta kontrolü de burada olmalı (şu an manuel filtresiz versiyon)
                
                hedef = last['Close'] * 1.15 # %15 Hedef
                stop = st_val # Stop-Loss, SuperTrend çizgisidir.
                
                signal_text = f"✅ *{hisse}* ({sektor})\n" \
                              f"Giriş: {last['Close']:.2f} TL\n" \
                              f"Hedef: {hedef:.2f} TL (Beklenen %15)\n" \
                              f"Stop-Loss: {stop:.2f} TL\n"
                
                secilenler.append(signal_text)
                used_sectors.add(sektor)
                
                positions_to_save.append({
                    'hisse': hisse,
                    'stop_fiyat': stop
                })
                break

    if secilenler:
        report += "⭐ *YENİ HAFTALIK AL SİNYALLERİ* ⭐\n"
        report += "".join(secilenler)
        report += "\n\n⚠️ _Yatırım tavsiyesi değildir. Robotik analiz sonucudur._"
    else:
        report += "Bu hafta uygun kriterde hisse bulunamadı. Nakitte kalmak mantıklı olabilir."

    send_telegram(report)
    save_positions(positions_to_save)


# --- PERŞEMBE KONTROLÜ (SAT SİNYALİ) ---
def persembe_kontrolu():
    positions = load_positions()
    
    if not positions:
        send_telegram("🗓️ *PERŞEMBE KONTROL:* Geçen haftadan takip edilecek pozisyon bulunamadı.")
        return

    rapor = f"🗓️ *PERŞEMBE KAPANIŞ KONTROLÜ* ({date.today().strftime('%d.%m.%Y')})\n\n"
    kapananlar = []
    devam_edenler = []
    new_positions = []

    for pos in positions:
        hisse = pos['hisse']
        stop_fiyat = pos['stop_fiyat']
        
        df = get_weekly_supertrend(hisse)
        if df is None: continue
        
        last_close = df.iloc[-1]['Close']
        last_trend = df.iloc[-1]['Trend']
        
        # SAT SİNYALİ: Trend Kırmızıya döndüyse VEYA Fiyat Stop-Loss'a değdiyse
        if last_trend == -1 or last_close < stop_fiyat:
            kapananlar.append(f"🔴 *{hisse}* → **KAPAT** (Fiyat: {last_close:.2f} TL). Trend bozuldu / Stop-Loss'a değdi.")
        else:
            devam_edenler.append(f"🟢 *{hisse}* → **DEVAM** (Fiyat: {last_close:.2f} TL). Trend sağlam.")
            new_positions.append(pos) # Devam edenleri bir sonraki hafta için kaydet

    if kapananlar:
        rapor += "*POZİSYON KAPATMA SİNYALLERİ (KAR/ZARAR GERÇEKLEŞTİ)*\n"
        rapor += "\n".join(kapananlar)
        rapor += "\n"
        
    if devam_edenler:
        rapor += "*DEVAM EDEN POZİSYONLAR*\n"
        rapor += "\n".join(devam_edenler)

    send_telegram(rapor)
    save_positions(new_positions) # Sadece devam edenleri kaydet

# --- ANA KONTROL (GÜN KONTROLÜ İÇİN DÜZELTİLDİ) ---
if __name__ == "__main__":
    gun = datetime.now().weekday() # 0=Pazartesi, 6=Pazar
    
    # Pazar (6) ise AL Sinyali çalışır
    if gun == 6:
        print("Pazar Taraması Başlatılıyor...")
        pazar_taramasi()
    
    # Perşembe (3) ise SAT Sinyali çalışır
    elif gun == 3:
        print("Perşembe Kontrolü Başlatılıyor...")
        persembe_kontrolu()
    
    else:
        print(f"Beklemede... Bugün işlem günü değil. (Pazar veya Perşembe bekleniyor)")
