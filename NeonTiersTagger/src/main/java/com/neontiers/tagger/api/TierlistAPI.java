package com.neontiers.tagger.api;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.client.MinecraftClient;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

public class TierlistAPI {
    private static final String DEFAULT_API_URL = "https://neontiers.vercel.app/api/tests";
    private static final long CACHE_DURATION_MS = 30000; // 30 seconds cache
    
    private String apiUrl;
    private final Map<String, PlayerRanks> rankCache;
    private long lastCacheUpdate;
    private final Gson gson;
    
    public TierlistAPI() {
        this.apiUrl = DEFAULT_API_URL;
        this.rankCache = new HashMap<>();
        this.lastCacheUpdate = 0;
        this.gson = new Gson();
    }
    
    public void setApiUrl(String url) {
        this.apiUrl = url;
        rankCache.clear();
    }
    
    public String getApiUrl() {
        return apiUrl;
    }
    
    public void updateCache(MinecraftClient client) {
        long currentTime = System.currentTimeMillis();
        if (currentTime - lastCacheUpdate < CACHE_DURATION_MS) {
            return; // Cache still valid
        }
        
        if (client.world == null || client.player == null) {
            return;
        }
        
        // Fetch ranks for all players in the world asynchronously
        CompletableFuture.runAsync(() -> {
            try {
                fetchAllPlayerRanks();
                lastCacheUpdate = currentTime;
            } catch (Exception e) {
                System.err.println("Failed to update rank cache: " + e.getMessage());
            }
        });
    }
    
    private void fetchAllPlayerRanks() throws Exception {
        URL url = new URL(apiUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(5000);
        
        if (conn.getResponseCode() != 200) {
            throw new Exception("API returned status: " + conn.getResponseCode());
        }
        
        BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
        StringBuilder response = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            response.append(line);
        }
        reader.close();
        
        JsonObject json = gson.fromJson(response.toString(), JsonObject.class);
        JsonArray tests = json.getAsJsonArray("tests");
        
        if (tests != null) {
            Map<String, PlayerRanks> newCache = new HashMap<>();
            
            for (JsonElement element : tests) {
                JsonObject test = element.getAsJsonObject();
                String username = test.get("username").getAsString();
                String gamemode = test.get("gamemode").getAsString();
                String rank = test.get("rank").getAsString();
                int points = test.get("points").getAsInt();
                
                PlayerRanks playerRanks = newCache.computeIfAbsent(username, k -> new PlayerRanks(username));
                playerRanks.addRank(gamemode, rank, points);
            }
            
            // Update cache atomically
            synchronized (rankCache) {
                rankCache.clear();
                rankCache.putAll(newCache);
            }
        }
    }
    
    public PlayerRanks getPlayerRanks(String username) {
        synchronized (rankCache) {
            return rankCache.get(username);
        }
    }
    
    public int getTotalPoints(String username) {
        PlayerRanks ranks = getPlayerRanks(username);
        return ranks != null ? ranks.getTotalPoints() : 0;
    }
    
    public String getHighestRank(String username) {
        PlayerRanks ranks = getPlayerRanks(username);
        return ranks != null ? ranks.getHighestRank() : null;
    }
    
    public Map<String, String> getAllRanks(String username) {
        PlayerRanks ranks = getPlayerRanks(username);
        return ranks != null ? ranks.getAllRanks() : new HashMap<>();
    }
    
    public static class PlayerRanks {
        private final String username;
        private final Map<String, RankInfo> ranks;
        private int totalPoints;
        
        public PlayerRanks(String username) {
            this.username = username;
            this.ranks = new HashMap<>();
            this.totalPoints = 0;
        }
        
        public void addRank(String gamemode, String rank, int points) {
            ranks.put(gamemode.toLowerCase(), new RankInfo(rank, points));
            totalPoints += points;
        }
        
        public String getUsername() {
            return username;
        }
        
        public int getTotalPoints() {
            return totalPoints;
        }
        
        public String getHighestRank() {
            String highestRank = null;
            int highestPoints = -1;
            
            for (RankInfo info : ranks.values()) {
                if (info.points > highestPoints) {
                    highestPoints = info.points;
                    highestRank = info.rank;
                }
            }
            
            return highestRank;
        }
        
        public Map<String, String> getAllRanks() {
            Map<String, String> result = new HashMap<>();
            for (Map.Entry<String, RankInfo> entry : ranks.entrySet()) {
                result.put(entry.getKey(), entry.getValue().rank);
            }
            return result;
        }
        
        public RankInfo getRankInfo(String gamemode) {
            return ranks.get(gamemode.toLowerCase());
        }
    }
    
    public static class RankInfo {
        public final String rank;
        public final int points;
        
        public RankInfo(String rank, int points) {
            this.rank = rank;
            this.points = points;
        }
    }
}
