package com.myndlens.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.Toast;

/**
 * Minimal SMS Compose Activity
 * Required for MyndLens to be recognized as an SMS app
 * 
 * This activity handles sms: and smsto: intents
 * Redirects to native SMS app for actual composition
 */
public class ComposeSmsActivity extends Activity {
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        Intent intent = getIntent();
        String action = intent.getAction();
        Uri data = intent.getData();
        
        // Extract phone number and message if present
        String phoneNumber = "";
        String message = "";
        
        if (data != null) {
            phoneNumber = data.getSchemeSpecificPart();
        }
        
        if (Intent.ACTION_SENDTO.equals(action) || Intent.ACTION_SEND.equals(action)) {
            // User wants to compose SMS
            // Redirect to default SMS app (not MyndLens)
            Toast.makeText(this, "Opening native SMS app...", Toast.LENGTH_SHORT).show();
            
            try {
                Intent smsIntent = new Intent(Intent.ACTION_VIEW);
                smsIntent.setData(Uri.parse("sms:" + phoneNumber));
                if (!message.isEmpty()) {
                    smsIntent.putExtra("sms_body", message);
                }
                smsIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(smsIntent);
            } catch (Exception e) {
                Toast.makeText(this, "Could not open SMS app", Toast.LENGTH_SHORT).show();
            }
        }
        
        // Close this activity immediately
        finish();
    }
}
