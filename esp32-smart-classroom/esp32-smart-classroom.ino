/*
  ================================================================
  INTELLIGENT CLASSROOM SAVER (ICS)
  Demo Firmware — Single Room Model v2.7
  Changes from v2.4:
    - Live heartbeat to dashboard every 10 seconds
    - Fan timeout after 60 seconds
    - Step-by-step LCD feedback
  ================================================================
*/

#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "DHT.h"
#include <RTClib.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_task_wdt.h>
#include "time.h"
#include "mbedtls/md.h"

// ================================================================
// CONFIGURATION
// ================================================================

const char* WIFI_SSID  = "Galaxy S21 5G 07f2";
const char* WIFI_PASS  = "amnl1883";
const char* API_BASE   = "https://intelligent-classroom-saver-api.onrender.com";
const char* API_KEY    = "Xboay1VejM+RC7Pvh2GZLgzMuJKU0dB2QzUoXfISHUc=";
const char* ROOM_ID    = "486f969a-0a2b-46c1-8156-cbb7ff2468ef";

const char* NTP_SERVER = "pool.ntp.org";
const long  GMT_OFFSET = 3600;
const int   DST_OFFSET = 0;

// ================================================================
// PINS
// ================================================================

#define SCK_PIN        18
#define MISO_PIN       19
#define MOSI_PIN       23
#define RST_ENTRY_PIN  27
#define RST_EXIT_PIN   26
#define SS_ENTRY_PIN   5
#define SS_EXIT_PIN    4
#define RELAY_DOOR     13
#define RELAY_LIGHT    33
#define RELAY_FAN      32
#define BUZZER_PIN     25
#define SDA_PIN        21
#define SCL_PIN        22
#define DHTPIN         15
#define DHTTYPE        DHT22
#define LDR_PIN        34

// ================================================================
// THRESHOLDS AND TIMING
// ================================================================

#define TEMP_ALERT_THRESHOLD   35.0
#define LDR_DARK_THRESHOLD     50
#define FAN_ON_TEMP            28.0
#define FAN_OFF_TEMP           26.0
#define DOOR_UNLOCK_SECONDS    5
#define LCD_CLEAR_AFTER_MS     4000
#define WDT_TIMEOUT_SECONDS    30

const unsigned long SCAN_DELAY          = 3000;
const unsigned long ENV_INTERVAL        = 300000;
const unsigned long RETRY_INTERVAL      = 60000;
const unsigned long WIFI_CHECK_INTERVAL = 30000;
const unsigned long BG_UPLOAD_INTERVAL  = 5000;
const unsigned long HEARTBEAT_INTERVAL  = 10000;  // NEW: live dashboard every 10s
const unsigned long FAN_TIMEOUT         = 60000;  // NEW: fan auto-off after 60s

// ================================================================
// OBJECTS
// ================================================================

MFRC522           entryReader(SS_ENTRY_PIN, RST_ENTRY_PIN);
MFRC522           exitReader(SS_EXIT_PIN,   RST_EXIT_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
RTC_DS3231        rtc;
DHT               dht(DHTPIN, DHTTYPE);
Preferences       prefs;

// ================================================================
// CARD CACHE
// ================================================================

struct CardRecord {
  String uidFast;
  String userId;
  String role;
  String name;
};

const int MAX_CARDS = 50;
CardRecord cardCache[MAX_CARDS];
int cacheSize = 0;

// ================================================================
// BACKGROUND EVENT QUEUE
// ================================================================

struct PendingEvent {
  String cardUID;
  String reader;
  String timestamp;
};
PendingEvent pendingEvents[20];
int pendingCount = 0;
unsigned long lastBgUpload = 0;

// ================================================================
// PERSISTENT STORAGE
// ================================================================

void saveCacheToNVS() {
  prefs.begin("cardcache", false);
  prefs.putInt("size", cacheSize);
  for (int i = 0; i < cacheSize; i++) {
    String prefix = "c" + String(i);
    prefs.putString((prefix + "f").c_str(), cardCache[i].uidFast);
    prefs.putString((prefix + "i").c_str(), cardCache[i].userId);
    prefs.putString((prefix + "r").c_str(), cardCache[i].role);
    prefs.putString((prefix + "n").c_str(), cardCache[i].name);
  }
  prefs.end();
  Serial.println("Cache saved to NVS: " + String(cacheSize) + " cards");
}

bool loadCacheFromNVS() {
  prefs.begin("cardcache", true);
  int saved = prefs.getInt("size", 0);
  if (saved == 0) {
    prefs.end();
    Serial.println("NVS: no saved cache found");
    return false;
  }
  cacheSize = 0;
  for (int i = 0; i < saved && i < MAX_CARDS; i++) {
    String prefix = "c" + String(i);
    cardCache[i].uidFast = prefs.getString((prefix + "f").c_str(), "");
    cardCache[i].userId  = prefs.getString((prefix + "i").c_str(), "");
    cardCache[i].role    = prefs.getString((prefix + "r").c_str(), "");
    cardCache[i].name    = prefs.getString((prefix + "n").c_str(), "");
    if (cardCache[i].uidFast.length() > 0) cacheSize++;
  }
  prefs.end();
  Serial.println("NVS: loaded " + String(cacheSize) + " cards from flash");
  return cacheSize > 0;
}

// ================================================================
// PRESENCE TRACKING
// ================================================================

const int MAX_PRESENT = 50;
String presentUsers[MAX_PRESENT];
int presentCount = 0;

bool isInsideRoom(String userId) {
  for (int i = 0; i < presentCount; i++) {
    if (presentUsers[i] == userId) return true;
  }
  return false;
}

void markEntered(String userId) {
  if (presentCount >= MAX_PRESENT) return;
  if (isInsideRoom(userId)) return;
  presentUsers[presentCount++] = userId;
  Serial.println("Marked entered: " + userId);
}

void markExited(String userId) {
  for (int i = 0; i < presentCount; i++) {
    if (presentUsers[i] == userId) {
      for (int j = i; j < presentCount - 1; j++) {
        presentUsers[j] = presentUsers[j + 1];
      }
      presentCount--;
      Serial.println("Marked exited: " + userId);
      return;
    }
  }
}

// ================================================================
// STATE FLAGS
// ================================================================

bool cacheLoaded  = false;
int  currentOccupancy = 0;
bool lightsOn         = false;
bool fanOn            = false;
unsigned long fanStartedAt = 0;   // NEW: fan timeout tracking

unsigned long lastScanTime    = 0;
unsigned long lastEnvUpload   = 0;
unsigned long lastRetryCheck  = 0;
unsigned long lastWifiCheck   = 0;
unsigned long lastHeartbeat   = 0;  // NEW: heartbeat tracking
unsigned long lcdMessageTime  = 0;
bool          lcdShowingMsg   = false;

// ================================================================
// NON-BLOCKING DOOR
// ================================================================

bool          doorUnlocked = false;
unsigned long doorOpenedAt = 0;

void unlockDoor() {
  Serial.println("Door: unlocking");
  digitalWrite(RELAY_DOOR, LOW);
  doorUnlocked = true;
  doorOpenedAt = millis();
}

void updateDoor() {
  if (doorUnlocked &&
      millis() - doorOpenedAt >= (DOOR_UNLOCK_SECONDS * 1000UL)) {
    digitalWrite(RELAY_DOOR, HIGH);
    doorUnlocked = false;
    Serial.println("Door: relocked");
  }
}

// ================================================================
// BUZZER (active buzzer — uses digitalWrite, not PWM)
// ================================================================

void beepGrant() {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(100);
  digitalWrite(BUZZER_PIN, LOW);
  delay(60);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(300);
  digitalWrite(BUZZER_PIN, LOW);
}

void beepDeny() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(180);
    digitalWrite(BUZZER_PIN, LOW);
    delay(100);
  }
}

void beepShort() {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(80);
  digitalWrite(BUZZER_PIN, LOW);
}

// ================================================================
// LCD
// ================================================================

void lcdIdle() {
  DateTime now = rtc.now();
  float temp   = dht.readTemperature();
  char line1[17];
  sprintf(line1, "ICS  %02d:%02d", now.hour(), now.minute());
  char line2[17];
  if (!isnan(temp)) {
    sprintf(line2, "In:%d  %.1fC", currentOccupancy, temp);
  } else {
    sprintf(line2, "Occupancy: %d", currentOccupancy);
  }
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(line1);
  lcd.setCursor(0, 1); lcd.print(line2);
}

void lcdShow(String line1, String line2 = "") {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  if (line2.length() > 0) {
    lcd.setCursor(0, 1);
    lcd.print(line2.substring(0, 16));
  }
  lcdMessageTime = millis();
  lcdShowingMsg  = true;
}

void lcdTick() {
  if (lcdShowingMsg &&
      millis() - lcdMessageTime >= LCD_CLEAR_AFTER_MS) {
    lcdShowingMsg = false;
    lcdIdle();
  }
  static unsigned long lastIdleRefresh = 0;
  if (!lcdShowingMsg && millis() - lastIdleRefresh >= 15000) {
    lastIdleRefresh = millis();
    lcdIdle();
  }
}

// ================================================================
// LIGHTS
// ================================================================

void updateLights() {
  static bool lastState = false;
  static unsigned long lastChangeMs = 0;
  const unsigned long DEBOUNCE_MS = 2000;

  int  ldrValue   = analogRead(LDR_PIN);
  bool isDark     = (ldrValue < LDR_DARK_THRESHOLD);
  bool shouldBeOn = (currentOccupancy > 0) && isDark;

  if (shouldBeOn != lastState && millis() - lastChangeMs >= DEBOUNCE_MS) {
    lastState = shouldBeOn;
    digitalWrite(RELAY_LIGHT, shouldBeOn ? HIGH : LOW);
    lightsOn = shouldBeOn;
    lastChangeMs = millis();
    Serial.print("LDR: ");
    Serial.print(ldrValue);
    Serial.println(shouldBeOn ? " -> Lights: ON" : " -> Lights: OFF");
  }
}

// ================================================================
// FAN (temperature-based, only when room is occupied, 60s timeout)
// ================================================================

void updateFan() {
  float temp = dht.readTemperature();
  if (isnan(temp)) return;

  bool roomOccupied = (currentOccupancy > 0);
  bool tooHot       = (temp > FAN_ON_TEMP);
  bool tooCold      = (temp < FAN_OFF_TEMP);
  bool timedOut     = (fanOn && (millis() - fanStartedAt >= FAN_TIMEOUT));

  bool shouldBeOn = roomOccupied && tooHot && !timedOut;

  if (shouldBeOn && !fanOn) {
    digitalWrite(RELAY_FAN, LOW);
    fanOn = true;
    fanStartedAt = millis();
    Serial.println("Fan: ON (" + String(temp) + " C, " + String(currentOccupancy) + " inside)");
  }
  else if (fanOn && (!roomOccupied || tooCold || timedOut)) {
    digitalWrite(RELAY_FAN, HIGH);
    fanOn = false;
    if (!roomOccupied) {
      Serial.println("Fan: OFF (room empty)");
    } else if (timedOut) {
      Serial.println("Fan: OFF (timeout)");
    } else {
      Serial.println("Fan: OFF (" + String(temp) + " C)");
    }
  }
}

// ================================================================
// SHA-256
// ================================================================

String sha256(String input) {
  byte hash[32];
  mbedtls_md_context_t ctx;
  const mbedtls_md_info_t* info =
    mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, info, 0);
  mbedtls_md_starts(&ctx);
  mbedtls_md_update(&ctx,
    (const unsigned char*)input.c_str(), input.length());
  mbedtls_md_finish(&ctx, hash);
  mbedtls_md_free(&ctx);
  String result = "";
  for (int i = 0; i < 32; i++) {
    if (hash[i] < 0x10) result += "0";
    result += String(hash[i], HEX);
  }
  return result;
}

// ================================================================
// UID
// ================================================================

String readUID(MFRC522 &reader) {
  String uid = "";
  for (byte i = 0; i < reader.uid.size; i++) {
    if (reader.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(reader.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

CardRecord* findInCache(String rawUID) {
  String hashed = sha256(rawUID);
  for (int i = 0; i < cacheSize; i++) {
    if (cardCache[i].uidFast == hashed) return &cardCache[i];
  }
  return nullptr;
}

// ================================================================
// TIME
// ================================================================

String getRTCTimestamp() {
  DateTime now = rtc.now();
  char buf[25];
  sprintf(buf, "%04d-%02d-%02dT%02d:%02d:%02dZ",
    now.year(), now.month(), now.day(),
    now.hour(), now.minute(), now.second());
  return String(buf);
}

String getRTCShort() {
  DateTime now = rtc.now();
  char buf[6];
  sprintf(buf, "%02d:%02d", now.hour(), now.minute());
  return String(buf);
}

// ================================================================
// WI-FI
// ================================================================

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  lcdShow("Connecting...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 20) {
    delay(500);
    tries++;
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi OK: " + WiFi.localIP().toString());
    lcdShow("WiFi Connected", WiFi.localIP().toString());
  } else {
    Serial.println("\nWiFi failed — offline mode");
    lcdShow("WiFi Failed", "Offline Mode");
  }
  delay(1200);
}

void checkWifi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi dropped — reconnecting");
    WiFi.disconnect();
    delay(500);
    connectWifi();
  }
}

void syncNTP() {
  if (WiFi.status() != WL_CONNECTED) return;
  configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
  struct tm t;
  if (!getLocalTime(&t)) return;
  rtc.adjust(DateTime(
    t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
    t.tm_hour, t.tm_min, t.tm_sec));
  Serial.println("RTC synced");
}

// ================================================================
// API HEADERS
// ================================================================

void addHeaders(HTTPClient &http) {
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
}

// ================================================================
// LIVE HEARTBEAT — sends current status to dashboard every 10s
// ================================================================

void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return;

  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();
  int   ldr  = analogRead(LDR_PIN);

  HTTPClient http;
  http.begin(String(API_BASE) + "/api/heartbeat");
  addHeaders(http);
  http.setTimeout(3000);

  DynamicJsonDocument doc(512);
  doc["room_id"]        = ROOM_ID;
  doc["occupancy"]      = currentOccupancy;
  doc["door_locked"]    = !doorUnlocked;
  doc["lights_on"]      = lightsOn;
  doc["fan_on"]         = fanOn;
  doc["temperature"]    = isnan(temp) ? 0 : temp;
  doc["humidity"]       = isnan(hum) ? 0 : hum;
  doc["light_level"]    = ldr;
  doc["timestamp"]      = getRTCTimestamp();

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  http.end();
}

// ================================================================
// FETCH CARD CACHE
// ================================================================

bool fetchCardCache() {
  if (WiFi.status() != WL_CONNECTED) return false;
  lcdShow("Syncing cards..", "");
  HTTPClient http;
  http.begin(String(API_BASE) + "/api/users");
  addHeaders(http);
  http.setTimeout(10000);
  int code = http.GET();
  if (code == 200) {
    String payload = http.getString();
    http.end();
    DynamicJsonDocument doc(8192);
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
      Serial.println("Cache JSON error: " + String(err.c_str()));
      return false;
    }
    JsonArray arr = doc.as<JsonArray>();
    cacheSize = 0;
    for (JsonObject entry : arr) {
      if (cacheSize >= MAX_CARDS) break;
      cardCache[cacheSize++] = {
        entry["uid_fast"] | "",
        entry["user_id"]  | "",
        entry["role"]     | "",
        entry["name"]     | ""
      };
    }
    Serial.println("Cache fetched: " + String(cacheSize) + " cards");
    lcdShow("Cards synced", String(cacheSize) + " loaded");
    saveCacheToNVS();
    cacheLoaded = true;
    delay(800);
    return true;
  } else {
    http.end();
    Serial.println("Cache fetch failed: " + String(code));
    return false;
  }
}

// ================================================================
// PERIODIC RETRY
// ================================================================

void retryMissingData() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (!cacheLoaded) {
    Serial.println("Retry: fetching card cache");
    lcdShow("Retrying...", "Card sync");
    fetchCardCache();
  }
}

// ================================================================
// BACKGROUND EVENT QUEUE
// ================================================================

void queueEvent(String rawUID, String reader) {
  if (pendingCount >= 20) {
    Serial.println("Event queue full – dropping oldest");
    for (int i = 0; i < 19; i++) {
      pendingEvents[i] = pendingEvents[i + 1];
    }
    pendingCount = 19;
  }
  pendingEvents[pendingCount].cardUID   = rawUID;
  pendingEvents[pendingCount].reader    = reader;
  pendingEvents[pendingCount].timestamp = getRTCTimestamp();
  pendingCount++;
  Serial.println("Queued event (" + reader + ") – pending: " + String(pendingCount));
}

bool postAccessEvent(String rawUID, String reader, String timestamp, String &serverMessage) {
  serverMessage = "";
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  http.begin(String(API_BASE) + "/api/access");
  addHeaders(http);
  http.setTimeout(5000);

  DynamicJsonDocument doc(512);
  doc["room_id"]   = ROOM_ID;
  doc["card_uid"]  = rawUID;
  doc["reader"]    = reader;
  doc["timestamp"] = timestamp;

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  String payload = http.getString();
  http.end();

  if (code == 200) {
    DynamicJsonDocument response(512);
    DeserializationError err = deserializeJson(response, payload);
    if (!err) {
      serverMessage = response["message"] | "";
      String decision = response["decision"] | "";
      Serial.println("Access API: " + decision + " - " + serverMessage);
    } else {
      Serial.println("Access API response JSON error: " + String(err.c_str()));
    }
    return true;
  }

  Serial.println("Access API failed (" + String(code) + ") – will queue");
  return false;
}

void sendOrQueueAccessEvent(String rawUID, String reader) {
  String serverMessage = "";
  if (postAccessEvent(rawUID, reader, getRTCTimestamp(), serverMessage)) {
    if (serverMessage == "Access Granted - Attendance Marked") {
      lcdShow("Attendance", "Marked");
    }
    return;
  }
  queueEvent(rawUID, reader);
}

void uploadPendingEvents() {
  while (pendingCount > 0 && WiFi.status() == WL_CONNECTED) {
    String rawUID    = pendingEvents[0].cardUID;
    String reader    = pendingEvents[0].reader;
    String timestamp = pendingEvents[0].timestamp;

    String serverMessage = "";
    if (postAccessEvent(rawUID, reader, timestamp, serverMessage)) {
      Serial.println("Uploaded: " + rawUID + " [" + reader + "]");
      if (serverMessage == "Access Granted - Attendance Marked") {
        lcdShow("Attendance", "Marked");
      }
      for (int i = 0; i < pendingCount - 1; i++) {
        pendingEvents[i] = pendingEvents[i + 1];
      }
      pendingCount--;
    } else {
      Serial.println("Upload failed – will retry");
      break;
    }
    delay(200);
  }
}

// ================================================================
// HANDLE UNKNOWN CARD (server-dependent – only for registration)
// ================================================================

void handleUnknownCard(String rawUID) {
  Serial.println("Unknown UID: " + rawUID);
  if (WiFi.status() != WL_CONNECTED) {
    lcdShow("Not Registered", rawUID.substring(0, 16));
    beepDeny();
    return;
  }
  HTTPClient http;
  http.begin(String(API_BASE) + "/api/registration/status");
  addHeaders(http);
  http.setTimeout(5000);
  int code = http.GET();
  bool regActive = false;
  if (code == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, http.getString());
    regActive = doc["active"] | false;
  }
  http.end();
  if (regActive) {
    HTTPClient http2;
    http2.begin(String(API_BASE) + "/api/registration/uid");
    addHeaders(http2);
    http2.setTimeout(5000);
    DynamicJsonDocument body(256);
    body["uid"] = rawUID;
    String bodyStr;
    serializeJson(body, bodyStr);
    lcdShow("Registering...", rawUID.substring(0, 16));
    int code2 = http2.POST(bodyStr);
    http2.end();
    if (code2 == 200) {
      lcdShow("Card Registered", "See portal");
      beepGrant();
      Serial.println("Refreshing cache after registration");
      fetchCardCache();
    } else if (code2 == 409) {
      lcdShow("Already", "Registered");
      beepDeny();
    } else {
      lcdShow("Reg Failed", "Error " + String(code2));
      beepDeny();
    }
  } else {
    lcdShow("Not Registered", rawUID.substring(0, 16));
    beepDeny();
  }
}

// ================================================================
// PROCESS CARD SCAN (OFFLINE-FIRST)
// ================================================================

void processCard(String rawUID, String reader) {
  Serial.println("Scan: " + rawUID + " [" + reader + "]");
  CardRecord* record = findInCache(rawUID);

  if (record == nullptr) {
    handleUnknownCard(rawUID);
    return;
  }

  Serial.println("Found: " + record->name + " (" + record->role + ")");

  if (reader == "entry") {
    if (isInsideRoom(record->userId)) {
      Serial.println("Already inside: " + record->name);
      lcdShow("Already Inside", record->name.substring(0, 16));
      beepDeny();
      return;
    }

    markEntered(record->userId);
    currentOccupancy++;
    Serial.println("Occupancy: " + String(currentOccupancy));
    lcdShow("Welcome", record->name.substring(0, 16));
    beepGrant();
    unlockDoor();
    updateLights();
    sendOrQueueAccessEvent(rawUID, "entry");
  }

  else if (reader == "exit") {
    if (!isInsideRoom(record->userId)) {
      Serial.println("Not inside: " + record->name);
      lcdShow("Not Inside", record->name.substring(0, 16));
      beepDeny();
      return;
    }

    markExited(record->userId);
    if (currentOccupancy > 0) currentOccupancy--;
    Serial.println("Occupancy: " + String(currentOccupancy));
    lcdShow("Goodbye", record->name.substring(0, 16));
    beepGrant();
    unlockDoor();
    updateLights();
    sendOrQueueAccessEvent(rawUID, "exit");
  }
}

// ================================================================
// UPLOAD ENVIRONMENT
// ================================================================

void uploadEnvironment() {
  if (WiFi.status() != WL_CONNECTED) return;
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();
  int   ldr  = analogRead(LDR_PIN);
  if (isnan(temp) || isnan(hum)) {
    Serial.println("DHT22 read failed");
    return;
  }
  Serial.printf("Env: %.1fC  %.1f%%  LDR:%d\n", temp, hum, ldr);
  HTTPClient http;
  http.begin(String(API_BASE) + "/api/environment");
  addHeaders(http);
  http.setTimeout(8000);
  DynamicJsonDocument doc(512);
  doc["room_id"]     = ROOM_ID;
  doc["temperature"] = temp;
  doc["humidity"]    = hum;
  doc["light_level"] = ldr;
  doc["ac_setpoint"] = (temp > TEMP_ALERT_THRESHOLD) ? 18 : 24;
  doc["timestamp"]   = getRTCTimestamp();
  String body;
  serializeJson(doc, body);
  int code = http.POST(body);
  Serial.println("Env upload: " + String(code));
  http.end();
}

// ================================================================
// SETUP
// ================================================================

void setup() {
  Serial.begin(115200);
  delay(500);

  esp_task_wdt_config_t wdt_config = {
    .timeout_ms    = WDT_TIMEOUT_SECONDS * 1000,
    .idle_core_mask = 0,
    .trigger_panic  = true
  };
  esp_task_wdt_reconfigure(&wdt_config);
  esp_task_wdt_add(NULL);

  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  lcdShow("ICS Starting", "");

  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_ENTRY_PIN);
  pinMode(SS_ENTRY_PIN,  OUTPUT); digitalWrite(SS_ENTRY_PIN,  HIGH);
  pinMode(SS_EXIT_PIN,   OUTPUT); digitalWrite(SS_EXIT_PIN,   HIGH);
  pinMode(RST_ENTRY_PIN, OUTPUT);
  pinMode(RST_EXIT_PIN,  OUTPUT);

  entryReader.PCD_Init(); delay(50);
  exitReader.PCD_Init();  delay(50);

  Serial.print("Entry reader: ");
  Serial.println(entryReader.PCD_ReadRegister(MFRC522::VersionReg), HEX);
  Serial.print("Exit reader: ");
  Serial.println(exitReader.PCD_ReadRegister(MFRC522::VersionReg), HEX);

  if (!rtc.begin()) {
    Serial.println("RTC not found");
    lcdShow("RTC Error", "Check wiring");
    delay(2000);
  }

  dht.begin();

  pinMode(RELAY_DOOR,  OUTPUT); digitalWrite(RELAY_DOOR,  HIGH);
  pinMode(RELAY_LIGHT, OUTPUT); digitalWrite(RELAY_LIGHT, LOW);
  pinMode(RELAY_FAN,   OUTPUT); digitalWrite(RELAY_FAN,   HIGH);
  pinMode(BUZZER_PIN,  OUTPUT);
  pinMode(LDR_PIN,     INPUT);

  beepShort();

  bool nvsCacheOk = loadCacheFromNVS();
  if (nvsCacheOk) {
    cacheLoaded = true;
    lcdShow("Cache restored", String(cacheSize) + " cards");
    delay(1000);
  }

  connectWifi();
  syncNTP();

  bool fetchOk = fetchCardCache();
  if (!fetchOk && !nvsCacheOk) {
    lcdShow("No card data!", "Waiting for net");
    delay(2000);
  }

  lcdIdle();
  Serial.println("System ready. Cache loaded: " + String(cacheLoaded));
}

// ================================================================
// LOOP
// ================================================================

void loop() {
  unsigned long now = millis();
  esp_task_wdt_reset();

  // Background upload of queued attendance events
  if (pendingCount > 0 && now - lastBgUpload >= BG_UPLOAD_INTERVAL) {
    lastBgUpload = now;
    uploadPendingEvents();
  }

  // NEW: Live heartbeat to dashboard
  if (now - lastHeartbeat >= HEARTBEAT_INTERVAL) {
    lastHeartbeat = now;
    sendHeartbeat();
  }

  updateDoor();
  lcdTick();
  updateLights();
  updateFan();

  if (now - lastWifiCheck >= WIFI_CHECK_INTERVAL) {
    lastWifiCheck = now;
    checkWifi();
  }

  if (now - lastRetryCheck >= RETRY_INTERVAL) {
    lastRetryCheck = now;
    retryMissingData();
  }

  if (now - lastEnvUpload >= ENV_INTERVAL) {
    lastEnvUpload = now;
    uploadEnvironment();
  }

  if (now - lastScanTime < SCAN_DELAY) return;

  if (entryReader.PICC_IsNewCardPresent() &&
      entryReader.PICC_ReadCardSerial()) {
    String uid = readUID(entryReader);
    entryReader.PICC_HaltA();
    entryReader.PCD_StopCrypto1();
    lastScanTime = now;
    processCard(uid, "entry");
    return;
  }

  if (exitReader.PICC_IsNewCardPresent() &&
      exitReader.PICC_ReadCardSerial()) {
    String uid = readUID(exitReader);
    exitReader.PICC_HaltA();
    exitReader.PCD_StopCrypto1();
    lastScanTime = now;
    processCard(uid, "exit");
    return;
  }
}
