# Raspberry Pi kurulumu (gateway)

Bu belge Raspberry Pi 4 elimize geçince uygulanacak adımları içerir (Adım 11). Gateway yazılımı Python olduğu için aynı kod bilgisayarda da çalışır; Pi, gerçek LoRa gateway'i ve demo için gereklidir.

## 1. İşletim sistemi
1. Bilgisayarda **Raspberry Pi Imager**'ı kurun, microSD kartı takın.
2. İşletim sistemi: **Raspberry Pi OS Lite (64-bit)**.
3. Dişli simgesinden ayarlar: ana makine adı `afet-gw`, SSH açık (parola ile), kullanıcı adı ve parola, Wi-Fi bilgileri (varsa), saat dilimi.
4. Kartı yazıp Pi'ye takın, 5,1 V / 3 A adaptörle açın.

## 2. Bağlanma ve güncelleme
```
ssh <kullanıcı>@afet-gw.local
sudo apt update && sudo apt full-upgrade -y
sudo raspi-config nonint do_spi 0      # SPI'yi aç (LoRa modülü için)
```

## 3. Proje kurulumu
```
sudo apt install -y git python3-venv
git clone https://github.com/MelihAliCagman/afet-mesh.git
cd afet-mesh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env     # .env içine anahtarları yazın (repoya girmez)
venv/bin/python -m pytest gateway/tests sim/tests -q
```

## 4. Hizmetler (systemd)
`gateway/deploy/` altındaki birim dosyaları kullanıcı adının `pi` ve proje yolunun `/home/pi/afet-mesh` olduğunu varsayar; farklıysa dosyalarda düzeltin.
```
sudo cp gateway/deploy/afet-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now afet-dashboard afet-bridge
systemctl status afet-dashboard afet-bridge
```
Panel: `http://afet-gw.local:8000`

## 5. Kontrol listesi
- [ ] Pi açılıyor, SSH ile bağlanılıyor (düşük gerilim uyarısı yok: `vcgencmd get_throttled` çıktısı `0x0`)
- [ ] Testler geçiyor (`pytest`)
- [ ] Panel açılıyor
- [ ] `.env` dosyası `.gitignore`'da, repoda anahtar yok
- [ ] LoRa modülü bağlanınca (Faz 3): SPI pinleri `docs/protokol.md` ve modül datasheet'ine göre, 3,3 V, anten takılı
