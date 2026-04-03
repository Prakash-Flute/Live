package com.instadownloader;

import android.app.DownloadManager;
import android.app.ProgressDialog;
import android.content.Context;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.URLUtil;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import java.io.IOException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends AppCompatActivity {
    private EditText urlInput;
    private Button downloadBtn;
    private ProgressDialog progressDialog;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        urlInput = findViewById(R.id.urlInput);
        downloadBtn = findViewById(R.id.downloadBtn);
        
        progressDialog = new ProgressDialog(this);
        progressDialog.setMessage("🔍 Finding video...");
        progressDialog.setCancelable(false);
        
        downloadBtn.setOnClickListener(v -> {
            String url = urlInput.getText().toString().trim();
            if (url.isEmpty()) {
                Toast.makeText(this, "❌ Link paste karo!", Toast.LENGTH_SHORT).show();
                return;
            }
            if (!url.contains("instagram.com")) {
                Toast.makeText(this, "❌ Sirf Instagram links!", Toast.LENGTH_SHORT).show();
                return;
            }
            new DownloadTask().execute(url);
        });
    }
    
    private class DownloadTask extends AsyncTask<String, Void, String> {
        @Override
        protected void onPreExecute() {
            super.onPreExecute();
            progressDialog.show();
        }
        
        @Override
        protected String doInBackground(String... urls) {
            String videoUrl = urls[0];
            try {
                // Method 1: Using ssstik.io API
                Document doc = Jsoup.connect("https://ssstik.io/abc")
                    .data("id", videoUrl)
                    .data("locale", "en")
                    .post();
                
                Element link = doc.select("a[href*=download]").first();
                if (link != null) {
                    return link.attr("href");
                }
                
                // Method 2: Alternative parsing
                String html = doc.html();
                Pattern pattern = Pattern.compile("href=\"(https://[^\"]*\\.mp4[^\"]*)\"");
                Matcher matcher = pattern.matcher(html);
                if (matcher.find()) {
                    return matcher.group(1);
                }
                
            } catch (IOException e) {
                return "error:" + e.getMessage();
            }
            return null;
        }
        
        @Override
        protected void onPostExecute(String result) {
            progressDialog.dismiss();
            if (result == null) {
                Toast.makeText(MainActivity.this, "❌ Video nahi mila!", Toast.LENGTH_LONG).show();
                return;
            }
            if (result.startsWith("error:")) {
                Toast.makeText(MainActivity.this, "Error: " + result.substring(6), Toast.LENGTH_LONG).show();
                return;
            }
            downloadVideo(result);
        }
    }
    
    private void downloadVideo(String videoUrl) {
        try {
            String fileName = "Insta_" + System.currentTimeMillis() + ".mp4";
            
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(videoUrl));
            request.setTitle("Instagram Video");
            request.setDescription("Downloading...");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
            request.allowScanningByMediaScanner();
            
            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            dm.enqueue(request);
            
            Toast.makeText(this, "✅ Download shuru! Downloads folder check karo", Toast.LENGTH_LONG).show();
            urlInput.setText("");
        } catch (Exception e) {
            Toast.makeText(this, "❌ Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }
}
