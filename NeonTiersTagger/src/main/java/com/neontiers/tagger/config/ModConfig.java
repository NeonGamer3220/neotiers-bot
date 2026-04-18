package com.neontiers.tagger.config;

import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.Properties;

public class ModConfig {
    private static final String CONFIG_FILE = "config/neontiers-tagger.properties";
    
    private String apiUrl;
    private boolean showRanks;
    private boolean showPoints;
    private boolean showGamemodes;
    private int maxGamemodesDisplayed;
    private boolean enableCache;
    private int cacheDurationSeconds;
    
    public ModConfig() {
        loadDefaults();
    }
    
    private void loadDefaults() {
        this.apiUrl = "https://neontiers.vercel.app/api/tests";
        this.showRanks = true;
        this.showPoints = true;
        this.showGamemodes = true;
        this.maxGamemodesDisplayed = 3;
        this.enableCache = true;
        this.cacheDurationSeconds = 30;
    }
    
    public void load() {
        File configFile = new File(CONFIG_FILE);
        if (!configFile.exists()) {
            save(); // Create default config
            return;
        }
        
        Properties props = new Properties();
        try (FileReader reader = new FileReader(configFile)) {
            props.load(reader);
            
            this.apiUrl = props.getProperty("apiUrl", apiUrl);
            this.showRanks = Boolean.parseBoolean(props.getProperty("showRanks", String.valueOf(showRanks)));
            this.showPoints = Boolean.parseBoolean(props.getProperty("showPoints", String.valueOf(showPoints)));
            this.showGamemodes = Boolean.parseBoolean(props.getProperty("showGamemodes", String.valueOf(showGamemodes)));
            this.maxGamemodesDisplayed = Integer.parseInt(props.getProperty("maxGamemodesDisplayed", String.valueOf(maxGamemodesDisplayed)));
            this.enableCache = Boolean.parseBoolean(props.getProperty("enableCache", String.valueOf(enableCache)));
            this.cacheDurationSeconds = Integer.parseInt(props.getProperty("cacheDurationSeconds", String.valueOf(cacheDurationSeconds)));
        } catch (IOException e) {
            System.err.println("Failed to load config: " + e.getMessage());
        }
    }
    
    public void save() {
        File configDir = new File("config");
        if (!configDir.exists()) {
            configDir.mkdirs();
        }
        
        Properties props = new Properties();
        props.setProperty("apiUrl", apiUrl);
        props.setProperty("showRanks", String.valueOf(showRanks));
        props.setProperty("showPoints", String.valueOf(showPoints));
        props.setProperty("showGamemodes", String.valueOf(showGamemodes));
        props.setProperty("maxGamemodesDisplayed", String.valueOf(maxGamemodesDisplayed));
        props.setProperty("enableCache", String.valueOf(enableCache));
        props.setProperty("cacheDurationSeconds", String.valueOf(cacheDurationSeconds));
        
        try (FileWriter writer = new FileWriter(CONFIG_FILE)) {
            props.store(writer, "NeonTiersTagger Configuration");
        } catch (IOException e) {
            System.err.println("Failed to save config: " + e.getMessage());
        }
    }
    
    // Getters and setters
    public String getApiUrl() {
        return apiUrl;
    }
    
    public void setApiUrl(String apiUrl) {
        this.apiUrl = apiUrl;
    }
    
    public boolean isShowRanks() {
        return showRanks;
    }
    
    public void setShowRanks(boolean showRanks) {
        this.showRanks = showRanks;
    }
    
    public boolean isShowPoints() {
        return showPoints;
    }
    
    public void setShowPoints(boolean showPoints) {
        this.showPoints = showPoints;
    }
    
    public boolean isShowGamemodes() {
        return showGamemodes;
    }
    
    public void setShowGamemodes(boolean showGamemodes) {
        this.showGamemodes = showGamemodes;
    }
    
    public int getMaxGamemodesDisplayed() {
        return maxGamemodesDisplayed;
    }
    
    public void setMaxGamemodesDisplayed(int maxGamemodesDisplayed) {
        this.maxGamemodesDisplayed = maxGamemodesDisplayed;
    }
    
    public boolean isEnableCache() {
        return enableCache;
    }
    
    public void setEnableCache(boolean enableCache) {
        this.enableCache = enableCache;
    }
    
    public int getCacheDurationSeconds() {
        return cacheDurationSeconds;
    }
    
    public void setCacheDurationSeconds(int cacheDurationSeconds) {
        this.cacheDurationSeconds = cacheDurationSeconds;
    }
}
