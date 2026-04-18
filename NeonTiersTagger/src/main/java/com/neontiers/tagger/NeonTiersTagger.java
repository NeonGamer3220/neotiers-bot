package com.neontiers.tagger;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.neontiers.tagger.api.TierlistAPI;
import com.neontiers.tagger.render.RankRenderer;

public class NeonTiersTagger implements ModInitializer {
    public static final String MOD_ID = "neontiers-tagger";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    
    private static TierlistAPI api;
    private static RankRenderer renderer;
    
    @Override
    public void onInitialize() {
        LOGGER.info("NeonTiersTagger initializing...");
        
        // Initialize API client
        api = new TierlistAPI();
        
        // Initialize renderer
        renderer = new RankRenderer();
        
        // Register render event
        WorldRenderEvents.AFTER_TRANSLUCENT.register(context -> {
            renderer.render(context.matrixStack(), context.camera());
        });
        
        // Register tick event for cache updates
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            if (client.player != null && client.world != null) {
                api.updateCache(client);
            }
        });
        
        LOGGER.info("NeonTiersTagger initialized successfully!");
    }
    
    public static TierlistAPI getApi() {
        return api;
    }
    
    public static RankRenderer getRenderer() {
        return renderer;
    }
}
