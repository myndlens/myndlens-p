package com.myndlens.app;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.provider.Telephony;
import android.util.Log;

import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;
import com.facebook.react.bridge.WritableArray;
import com.facebook.react.bridge.WritableMap;
import com.facebook.react.bridge.WritableNativeArray;
import com.facebook.react.bridge.WritableNativeMap;

/**
 * Native module to read SMS messages
 * Exposes SMS reading functionality to React Native
 */
public class SmsModule extends ReactContextBaseJavaModule {
    private static final String TAG = "MyndLens_SmsModule";
    private final ReactApplicationContext reactContext;

    public SmsModule(ReactApplicationContext context) {
        super(context);
        this.reactContext = context;
    }

    @Override
    public String getName() {
        return "SmsModule";
    }

    /**
     * Read SMS messages from device
     * @param limit Maximum number of messages to read
     * @param promise Promise to return results
     */
    @ReactMethod
    public void readSmsMessages(int limit, Promise promise) {
        try {
            ContentResolver contentResolver = reactContext.getContentResolver();
            Uri uri = Telephony.Sms.CONTENT_URI;
            
            String[] projection = new String[] {
                Telephony.Sms._ID,
                Telephony.Sms.ADDRESS,
                Telephony.Sms.BODY,
                Telephony.Sms.DATE,
                Telephony.Sms.TYPE,
                Telephony.Sms.READ
            };
            
            Cursor cursor = contentResolver.query(
                uri,
                projection,
                null,
                null,
                Telephony.Sms.DATE + " DESC LIMIT " + limit
            );
            
            WritableArray messages = new WritableNativeArray();
            
            if (cursor != null && cursor.moveToFirst()) {
                do {
                    WritableMap message = new WritableNativeMap();
                    message.putString("id", cursor.getString(0));
                    message.putString("address", cursor.getString(1));
                    message.putString("body", cursor.getString(2));
                    message.putString("date", cursor.getString(3));
                    message.putString("type", cursor.getString(4)); // 1=inbox, 2=sent
                    message.putString("read", cursor.getString(5));
                    messages.pushMap(message);
                } while (cursor.moveToNext());
                
                cursor.close();
            }
            
            Log.d(TAG, "Read " + messages.size() + " SMS messages");
            promise.resolve(messages);
            
        } catch (Exception e) {
            Log.e(TAG, "Error reading SMS: " + e.getMessage());
            promise.reject("SMS_READ_ERROR", e.getMessage());
        }
    }

    /**
     * Check if app is default SMS app
     */
    @ReactMethod
    public void isDefaultSmsApp(Promise promise) {
        try {
            String packageName = reactContext.getPackageName();
            String defaultSmsPackage = Telephony.Sms.getDefaultSmsPackage(reactContext);
            boolean isDefault = packageName.equals(defaultSmsPackage);
            promise.resolve(isDefault);
        } catch (Exception e) {
            promise.reject("CHECK_DEFAULT_ERROR", e.getMessage());
        }
    }
}
