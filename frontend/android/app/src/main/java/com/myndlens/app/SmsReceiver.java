package com.myndlens.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.telephony.SmsMessage;
import android.util.Log;

/**
 * SMS Broadcast Receiver - receives incoming SMS
 * Required for MyndLens to be recognized as an SMS app
 */
public class SmsReceiver extends BroadcastReceiver {
    private static final String TAG = "MyndLens_SMS";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent.getAction() == null) return;

        String action = intent.getAction();
        Log.d(TAG, "SMS Action received: " + action);

        if (action.equals("android.provider.Telephony.SMS_DELIVER")) {
            // SMS delivered - extract messages
            Bundle bundle = intent.getExtras();
            if (bundle != null) {
                Object[] pdus = (Object[]) bundle.get("pdus");
                if (pdus != null) {
                    for (Object pdu : pdus) {
                        SmsMessage message = SmsMessage.createFromPdu((byte[]) pdu);
                        String sender = message.getDisplayOriginatingAddress();
                        String body = message.getDisplayMessageBody();
                        long timestamp = message.getTimestampMillis();
                        
                        Log.d(TAG, "SMS from: " + sender + ", body: " + body);
                        
                        // TODO: Send to React Native via event emitter
                        // For now, just log it - Digital Self can read from SMS database
                    }
                }
            }
        }
    }
}
