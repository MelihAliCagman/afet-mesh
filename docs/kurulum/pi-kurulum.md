# Raspberry Pi kurulumu (gateway)

Bilgisayar **Windows** kalabilir; Pi kendi işletim sistemiyle (Raspberry Pi OS) çalışır ve Windows'tan SSH ile yönetilir. Ubuntu'ya geçmek gerekmez.

## 0. Gerekenler
- Raspberry Pi 4 Model B, microSD kart (en az 16 GB)
- 5 V / 3 A USB-C güç (USB-C → USB-C kablo ve PD uyumlu şarj aleti olur)
- Ethernet kablosu ve diğer ucunu takacağınız yer: **modem/router/anahtarın LAN portu** veya duvar prizi
- Bilgisayarda microSD okuyucu (yoksa USB microSD okuyucu)
- İsteğe bağlı: HDMI kablo + USB klavye (sorun gidermek için)

## 0.1 Türkçe karakter ve yol uyarıları (baştan önlem)
- Windows kullanıcı klasörünüz Türkçe karakter içeriyorsa (ör. `C:\Users\...Çağman`), bazı araçlar sorun çıkarabilir. Çalışma ve yedek dosyalarını **yalnızca ASCII** yollarda tutun: proje `C:\afet-mesh`, kart yedeği `C:\afet-yedek`.
- Pi kullanıcı adı, ana makine adı, **parola**, Wi-Fi adı ve Wi-Fi parolasında Türkçe karakter (ç, ğ, ı, ö, ş, ü) ve AltGr gerektiren semboller (@, {, [, \ gibi) kullanmayın. Harf, rakam ve `-` yeterli; parola en az 12 karakter olsun.
- SSH, kullanıcı klasörüne `known_hosts` yazamazsa `ssh -o UserKnownHostsFile=C:\afet-yedek\known_hosts pi@afet-gw.local` kullanın.

## 0.2 Ağ seçenekleri (Pi'nin internete ihtiyacı var: güncelleme, git, pip)
Üç yol var; hangisi kolaysa onu seçin.
1. **Modem/router'a Ethernet:** en kolayı, ama modemin yanına gitmek gerekir.
2. **Telefon hotspot'u (kablosuz):** telefondan hotspot açın, 2,4 GHz ve WPA2 seçin, adı ve parolası ASCII olsun. Aynı Wi-Fi bilgisini Imager'a girin; bilgisayar da aynı hotspot'a bağlansın. Mobil veri kullanır (güncellemeler yüzlerce MB olabilir).
3. **Bilgisayardan internet paylaşımı (ICS), Pi'ye Ethernet:** bilgisayarda Ethernet (RJ45) portu gerekir (yoksa USB-Ethernet adaptörü). Windows'ta: Ayarlar > Ağ ve İnternet > Gelişmiş ağ ayarları > Diğer ağ bağdaştırıcısı seçenekleri > Wi-Fi'ye sağ tık > Özellikler > Paylaşım > "Diğer ağ kullanıcılarının bu bilgisayarın internet bağlantısı üzerinden bağlanmasına izin ver" ve ev ağı olarak **Ethernet**'i seçin. Pi'ye Ethernet takılınca 192.168.137.x adresi alır. Hata verirse: "Internet Connection Sharing" ve "Windows Defender Güvenlik Duvarı" hizmetlerinin çalıştığını kontrol edin; VPN açıksa kapatın; seçenek gri ise bağdaştırıcıyı devre dışı bırakıp yeniden etkinleştirin. `afet-gw.local` bulunamazsa `arp -a` ile 192.168.137.x adresini bulun.

## 0.3 Kartı yedekleme (silmeden önce)
1. Kartı okuyucuya takın. Windows "diski biçimlendirmeniz gerekiyor" derse **İptal'e basın, asla biçimlendirmeyin.**
2. Yalnızca küçük bir `bootfs` sürücüsü görünür (içeriğin çoğu Windows'un okuyamadığı ext4 bölümünde).
3. Tüm kartın kopyası için **Win32 Disk Imager** (sourceforge.net/projects/win32diskimager) kullanın: yönetici olarak çalıştırın, dosya olarak `C:\afet-yedek\sd-yedek.img` yazın, cihaz olarak kartın sürücü harfini seçin, **Read** (Oku) düğmesine basın. **Write'a basmayın** (yazmak kartı silerdi).
4. `C:\afet-yedek` diskinde kart boyutu kadar boş yer olmalı (16 GB). Bitince PowerShell'de `Get-FileHash C:\afet-yedek\sd-yedek.img` ile özeti kaydedin ve dosyayı ikinci bir yere (harici disk veya bulut) kopyalayın.

## 1. İşletim sistemini karta yazma (Windows)
1. **Raspberry Pi Imager**'ı indirip kurun (raspberrypi.com/software).
2. microSD'yi okuyucuya takın. **Kartın içindeki her şey silinecek.**
3. Imager: Cihaz = *Raspberry Pi 4*, İşletim sistemi = *Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)*, Depolama = microSD kart.
4. "Ayarları düzenle" (OS customisation):
   - Ana makine adı: `afet-gw`
   - Kullanıcı adı: `pi`, güçlü bir parola (parolayı kimseyle paylaşmayın, repoya yazmayın)
   - Wi-Fi: Ethernet kullanacaksanız boş bırakabilirsiniz
   - Saat dilimi: `Europe/Istanbul`, klavye düzeni: `tr`
   - Hizmetler sekmesi: **SSH'yi etkinleştir** (parola ile)
5. Yazmayı başlatın, bitince kartı çıkarın.

## 2. İlk açılış
1. Kartı Pi'nin altındaki yuvaya takın.
2. Ethernet kablosunu Pi'ye ve router/modem/anahtar portuna takın.
3. Güç kablosunu en son takın. Yeşil ACT ışığı yanıp sönmeli. İlk açılış 1-3 dakika sürer.

## 3. Bağlanma (Windows PowerShell)
```
ping afet-gw.local
ssh pi@afet-gw.local
```
- İlk bağlanmada "devam edilsin mi" sorusuna `yes` yazın, sonra parolayı girin.
- `afet-gw.local` bulunamazsa: modem arayüzünün bağlı cihazlar listesinden Pi'nin IP adresini bulup `ssh pi@<IP>` kullanın.
- Okul gibi ağlarda cihazlar birbirini görmeyebilir (istemci yalıtımı); o durumda kendi modeminizi veya küçük bir anahtar (switch) kullanın, ya da Pi'yi bilgisayara doğrudan Ethernet ile bağlayın (ping ve ssh aynı şekilde `afet-gw.local` ile denenir, kimi zaman 1-2 dakika sürer).

## 4. Güncelleme ve kontrol
```
sudo apt update && sudo apt full-upgrade -y
free -h                      # RAM miktarı
vcgencmd get_throttled       # güç kalitesi: 0x0 olmalı
cat /etc/os-release
sudo raspi-config nonint do_spi 0     # SPI'yi aç (LoRa modülü için, Faz 3)
sudo reboot
```
`get_throttled` `0x0` dışında bir değer verirse güç kablosu veya şarj aleti yetersizdir.

## 5. Proje kurulumu
```
sudo apt install -y git python3-venv
git clone https://github.com/MelihAliCagman/afet-mesh.git
cd afet-mesh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env     # .env içine anahtarları yazın (repoya girmez)
venv/bin/python -m pytest gateway/tests sim/tests -q
```

## 6. Hizmetler (systemd)
`gateway/deploy/` altındaki birim dosyaları kullanıcı adının `pi` ve proje yolunun `/home/pi/afet-mesh` olduğunu varsayar; farklıysa dosyalarda düzeltin.
```
sudo cp gateway/deploy/afet-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now afet-dashboard
systemctl status afet-dashboard
```
Panel yalnızca Pi'nin kendi içinde (`127.0.0.1`) dinler, ağa açık değildir (panelde kimlik doğrulama yok). Bilgisayardan açmak için SSH tüneli kullanın: bilgisayarda `ssh -L 8000:127.0.0.1:8000 pi@<Pi adresi>` ile bağlanıp tarayıcıda `http://127.0.0.1:8000` adresini açın. (Köprü hizmeti `afet-bridge`, `.env` içinde uzak sunucu adresi ve API anahtarı tanımlanınca etkinleştirilir.)

## 7. Kontrol listesi
- [ ] Pi açılıyor, `ssh` ile bağlanılıyor
- [ ] `vcgencmd get_throttled` çıktısı `0x0`
- [ ] Testler geçiyor (`pytest`)
- [ ] Panel bilgisayardan açılıyor
- [ ] `.env` dosyası repoda yok (`git status` temiz)
- [ ] LoRa modülü bağlanınca (Faz 3): SPI pinleri modül datasheet'ine göre, 3,3 V, anten takılı
