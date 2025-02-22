#include <FS.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <ESP8266WiFi.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <TOTP.h>
#include <sha1.h>
#include <SPI.h>
#include <Wire.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_MOSI   13
#define OLED_CLK   14
#define OLED_DC    5
#define OLED_CS    15
#define OLED_RESET 4
#define BUTTON_LEFT 12
#define BUTTON_RIGHT 2

#define MAX_HMAC_KEY_LENGTH 32


const char* defaultPin = "750128";
int currentIndex = 0;
const int TIME_STEP = 30;

struct OTPToken {
  uint8_t hmacKey[MAX_HMAC_KEY_LENGTH];
  char name[20];
  uint8_t keyLength;
};

struct EEPROMData {
  char ssid[32];
  char password[32];
  char storedPin[10];
  OTPToken otpTokens[32];
  int tokensCount;
};

EEPROMData eepromData;

TOTP myTOTP(eepromData.otpTokens[0].hmacKey, sizeof(eepromData.otpTokens[0].hmacKey));
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, OLED_MOSI, OLED_CLK, OLED_DC, OLED_RESET, OLED_CS);

void saveConfig() {
  DynamicJsonDocument doc(16384);
  doc["ssid"] = eepromData.ssid;
  doc["password"] = eepromData.password;
  doc["storedPin"] = eepromData.storedPin;
  doc["tokensCount"] = eepromData.tokensCount;
  JsonArray tokens = doc.createNestedArray("otpTokens");
  for (int i = 0; i < eepromData.tokensCount; ++i) {
    JsonObject token = tokens.createNestedObject();
    token["name"] = eepromData.otpTokens[i].name;
    token["keyLength"] = eepromData.otpTokens[i].keyLength;
    JsonArray secret = token.createNestedArray("secret");
    for (int j = 0; j < eepromData.otpTokens[i].keyLength; ++j) {
      secret.add(eepromData.otpTokens[i].hmacKey[j]);
    }
  }

  File configFile = LittleFS.open("/config.json", "w");
  if (!configFile) {
    Serial.println("CONFIG FAIL");
    return;
  }
  serializeJson(doc, configFile);
  configFile.close();
}

bool loadConfig() {
  File configFile = LittleFS.open("/config.json", "r");
  if (!configFile) {
    Serial.println("CONFIG FAIL");
    return false;
  }

  DynamicJsonDocument doc(16384);
  DeserializationError error = deserializeJson(doc, configFile);
  if (error) {
    Serial.println("CONFIG FAIL");
    return false;
  }

  strlcpy(eepromData.ssid, doc["ssid"] | "", sizeof(eepromData.ssid));
  strlcpy(eepromData.password, doc["password"] | "", sizeof(eepromData.password));
  strlcpy(eepromData.storedPin, doc["storedPin"] | defaultPin, sizeof(eepromData.storedPin));
  eepromData.tokensCount = doc["tokensCount"] | 0;

  JsonArray tokens = doc["otpTokens"];
  for (int i = 0; i < eepromData.tokensCount; ++i) {
    JsonObject token = tokens[i];
    strlcpy(eepromData.otpTokens[i].name, token["name"] | "", sizeof(eepromData.otpTokens[i].name));
    eepromData.otpTokens[i].keyLength = token["keyLength"] | 16;
    JsonArray secret = token["secret"];

    if (eepromData.otpTokens[i].keyLength > MAX_HMAC_KEY_LENGTH) {
      eepromData.otpTokens[i].keyLength = MAX_HMAC_KEY_LENGTH;
    }
    for (int j = 0; j < eepromData.otpTokens[i].keyLength; ++j) {
      eepromData.otpTokens[i].hmacKey[j] = secret[j];
    }
  }

  configFile.close();
  return true;
}


void displayConfigMessage() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Please configure");
  display.println("the ESP8266 using");
  display.println("the application.");
  display.println();
  display.print("Default PIN: ");
  display.println(defaultPin);
  display.display();
}

void checkAndSetDefaults() {
  bool needsSetup = false;

  if (strlen(eepromData.ssid) == 0) {
    needsSetup = true;
  }
  if (strlen(eepromData.password) == 0) {
    needsSetup = true;
  }
  if (strlen(eepromData.storedPin) == 0) {
    needsSetup = true;
    strcpy(eepromData.storedPin, defaultPin);
  }

  if (needsSetup) {
    displayConfigMessage();
    while (true) {
      if (Serial.available() > 0) {
        String request = Serial.readStringUntil('\n');
        handleRequest(request);
      }
      delay(10);
    }
  }
}

void changePin(String oldPin, String newPin) {
  if (oldPin == eepromData.storedPin) {
    strcpy(eepromData.storedPin, newPin.c_str());
    saveConfig();
    Serial.println("OK\r\n");
  } else {
    Serial.println("FAIL\r\n");
  }
}

void authenticate(String pin) {
  Serial.println(pin);
  if (pin == eepromData.storedPin) {
    Serial.println("OK\r\n");
  } else {
    Serial.println("FAIL\r\n");
  }
}

void changeWifi(String pin, const char* wifi, const char* passwd) {
  if (pin == eepromData.storedPin) {
    strcpy(eepromData.ssid, wifi);
    strcpy(eepromData.password, passwd);
    saveConfig();
    Serial.println("OK\r\n");
  } else {
    Serial.println("FAIL\r\n");
  }
}

void saveTokens(DynamicJsonDocument& doc) {
  if (doc["pin"] != eepromData.storedPin) {
    Serial.println("FAIL\r\n");
    return;
  }

  JsonArray tokens = doc["tokens"];
  eepromData.tokensCount = tokens.size();
  for (int i = 0; i < eepromData.tokensCount; ++i) {
    JsonObject token = tokens[i];
    eepromData.otpTokens[i].keyLength = token["secret"].size();

    if (eepromData.otpTokens[i].keyLength > MAX_HMAC_KEY_LENGTH) {
      Serial.println("FAIL: Key too long\r\n");
      return;
    }

    for (int j = 0; j < eepromData.otpTokens[i].keyLength; ++j) {
      eepromData.otpTokens[i].hmacKey[j] = token["secret"][j];
    }
    strcpy(eepromData.otpTokens[i].name, token["name"]);
  }
  saveConfig();
  Serial.println("OK\r\n");
}

void getTokens(String pin) {
  if (pin == eepromData.storedPin) {
    DynamicJsonDocument doc(16384);
    JsonArray tokens = doc.createNestedArray("tokens");
    for (int i = 0; i < eepromData.tokensCount; ++i) {
      JsonObject token = tokens.createNestedObject();
      token["name"] = eepromData.otpTokens[i].name;
      JsonArray secret = token.createNestedArray("secret");
      for (int j = 0; j < 20; ++j) {
        secret.add(eepromData.otpTokens[i].hmacKey[j]);
      }
    }
    String response;
    serializeJson(doc, response);
    Serial.println(response);
  } else {
    Serial.println("FAIL\r\n");
  }
}

void handleRequest(String request) {
  DynamicJsonDocument doc(16384);
  DeserializationError error = deserializeJson(doc, request);

  if (error) {
    Serial.print("FAIL");
    return;
  }

  String action = doc["action"];
  if (action == "auth") {
    authenticate(doc["pin"]);
  } else if (action == "change_pin") {
    changePin(doc["old_pin"], doc["new_pin"]);
  } else if (action == "call") {
    Serial.println("OK\r\n"); // {"action":"change_pin","old_pin":"750128","new_pin":"6425"}
  } else if (action == "change_wifi") {
    changeWifi(doc["pin"], doc["wifi"], doc["password"]);
  } else if (action == "save_tokens") {
    saveTokens(doc);
  } else if (action == "get_data") {
    getTokens(doc["pin"]);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_LEFT, INPUT_PULLUP);
  pinMode(BUTTON_RIGHT, INPUT_PULLUP);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    for (;;);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Connecting to wifi..");
  display.display();

  if (!LittleFS.begin()) {
    Serial.println("Failed to mount file system");
    return;
  }

  if (!loadConfig()) {
    checkAndSetDefaults();
  }

  WiFi.begin(eepromData.ssid, eepromData.password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(100);
  }
  display.println("Connected to WiFi.");
  display.display();

  display.println("Waiting for time sync");
  display.display();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  while (!time(nullptr)) {
    delay(1000);
  }
  display.println("Ready to work!");
  display.display();
  delay(1500);
}

void loop() {
  if (Serial.available() > 0) {
    String request = Serial.readStringUntil('\n');
    request.trim();
    handleRequest(request);
  }

  if (digitalRead(BUTTON_LEFT) == LOW) {
    currentIndex = (currentIndex - 1 + eepromData.tokensCount) % eepromData.tokensCount;
    myTOTP = TOTP(eepromData.otpTokens[currentIndex].hmacKey, eepromData.otpTokens[currentIndex].keyLength);
    delay(125);
  } else if (digitalRead(BUTTON_RIGHT) == LOW) {
    currentIndex = (currentIndex + 1) % eepromData.tokensCount;
    myTOTP = TOTP(eepromData.otpTokens[currentIndex].hmacKey, eepromData.otpTokens[currentIndex].keyLength);
    delay(125);
  }

  time_t now = time(nullptr);
  char* code = myTOTP.getCode(now);
  int remainingTime = TIME_STEP - (now % TIME_STEP);
  int barWidth = (remainingTime * SCREEN_WIDTH) / TIME_STEP;

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.print("OTP ");
  display.print(eepromData.otpTokens[currentIndex].name);
  display.print(" ");
  display.print(currentIndex);
  display.print("\nExpires in: ");
  display.print(remainingTime);
  display.print("s");
  display.setCursor(10, 25);
  display.setTextSize(3);
  display.print(code);
  display.fillRect(0, 60, barWidth, 4, SSD1306_WHITE);
  display.display();
}
