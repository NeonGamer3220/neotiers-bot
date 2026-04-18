package com.neontiers.tagger.render;

import com.mojang.blaze3d.systems.RenderSystem;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.render.BufferBuilder;
import net.minecraft.client.render.Camera;
import net.minecraft.client.render.Tessellator;
import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.VertexFormat;
import net.minecraft.client.render.VertexFormats;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.Matrix4f;
import net.minecraft.util.math.Vec3d;

import com.neontiers.tagger.NeonTiersTagger;
import com.neontiers.tagger.api.TierlistAPI;

import java.util.HashMap;
import java.util.Map;

public class RankRenderer {
    private static final float TAG_SCALE = 0.025f;
    private static final float TAG_OFFSET_Y = 0.5f;
    
    // Rank colors (ARGB format)
    private static final Map<String, Integer> RANK_COLORS = new HashMap<>();
    
    static {
        // HT ranks - Gold/Yellow tones
        RANK_COLORS.put("HT1", 0xFFFFD700); // Gold
        RANK_COLORS.put("HT2", 0xFFFFA500); // Orange
        RANK_COLORS.put("HT3", 0xFFFF8C00); // Dark Orange
        RANK_COLORS.put("HT4", 0xFFCD853F); // Peru
        RANK_COLORS.put("HT5", 0xFFD2B48C); // Tan
        
        // LT ranks - Silver/Blue tones
        RANK_COLORS.put("LT1", 0xFFC0C0C0); // Silver
        RANK_COLORS.put("LT2", 0xFFA9A9A9); // Dark Gray
        RANK_COLORS.put("LT3", 0xFF87CEEB); // Sky Blue
        RANK_COLORS.put("LT4", 0xFF4682B4); // Steel Blue
        RANK_COLORS.put("LT5", 0xFF5F9EA0); // Cadet Blue
        
        // Special ranks
        RANK_COLORS.put("Unranked", 0xFF808080); // Gray
        RANK_COLORS.put("Retired", 0xFF8B4513); // Saddle Brown
    }
    
    // Gamemode colors
    private static final Map<String, Integer> GAMEMODE_COLORS = new HashMap<>();
    
    static {
        GAMEMODE_COLORS.put("vanilla", 0xFF90EE90); // Light Green
        GAMEMODE_COLORS.put("uhc", 0xFFFF6347); // Tomato
        GAMEMODE_COLORS.put("pot", 0xFF9370DB); // Medium Purple
        GAMEMODE_COLORS.put("nethpot", 0xFFFF4500); // Orange Red
        GAMEMODE_COLORS.put("smp", 0xFF20B2AA); // Light Sea Green
        GAMEMODE_COLORS.put("sword", 0xFF4169E1); // Royal Blue
        GAMEMODE_COLORS.put("axe", 0xFF8B4513); // Saddle Brown
        GAMEMODE_COLORS.put("mace", 0xFFB8860B); // Dark Goldenrod
        GAMEMODE_COLORS.put("cart", 0xFF32CD32); // Lime Green
        GAMEMODE_COLORS.put("creeper", 0xFF00FF00); // Green
        GAMEMODE_COLORS.put("diasmp", 0xFF00CED1); // Dark Turquoise
        GAMEMODE_COLORS.put("ogvanilla", 0xFFFAFAD2); // Light Goldenrod
        GAMEMODE_COLORS.put("shieldlessuhc", 0xFFDC143C); // Crimson
        GAMEMODE_COLORS.put("spearmace", 0xFFDAA520); // Goldenrod
        GAMEMODE_COLORS.put("spearelytra", 0xFF87CEEB); // Sky Blue
    }
    
    public void render(MatrixStack matrices, Camera camera) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null || client.player == null) {
            return;
        }
        
        TierlistAPI api = NeonTiersTagger.getApi();
        
        for (PlayerEntity player : client.world.getPlayers()) {
            if (player == client.player) {
                continue; // Don't render tag for self
            }
            
            String username = player.getName().getString();
            TierlistAPI.PlayerRanks ranks = api.getPlayerRanks(username);
            
            if (ranks == null) {
                continue; // No rank data available
            }
            
            renderPlayerTag(matrices, camera, player, ranks);
        }
    }
    
    private void renderPlayerTag(MatrixStack matrices, Camera camera, PlayerEntity player, TierlistAPI.PlayerRanks ranks) {
        Vec3d playerPos = player.getPos();
        Vec3d cameraPos = camera.getPos();
        
        double x = playerPos.x - cameraPos.x;
        double y = playerPos.y - cameraPos.y + player.getHeight() + TAG_OFFSET_Y;
        double z = playerPos.z - cameraPos.z;
        
        matrices.push();
        matrices.translate(x, y, z);
        matrices.multiply(camera.getRotation());
        matrices.scale(-TAG_SCALE, -TAG_SCALE, TAG_SCALE);
        
        Matrix4f matrix = matrices.peek().getPositionMatrix();
        Tessellator tessellator = Tessellator.getInstance();
        BufferBuilder buffer = tessellator.getBuffer();
        
        // Render main rank (highest rank)
        String highestRank = ranks.getHighestRank();
        if (highestRank != null) {
            int color = RANK_COLORS.getOrDefault(highestRank, 0xFFFFFFFF);
            renderText(matrix, buffer, highestRank, 0, 0, color, true);
        }
        
        // Render total points
        int totalPoints = ranks.getTotalPoints();
        String pointsText = totalPoints + " pts";
        renderText(matrix, buffer, pointsText, 0, 10, 0xFFFFFFFF, false);
        
        // Render top 3 gamemode ranks
        Map<String, String> allRanks = ranks.getAllRanks();
        int yOffset = 20;
        int count = 0;
        
        for (Map.Entry<String, String> entry : allRanks.entrySet()) {
            if (count >= 3) break;
            
            String gamemode = entry.getKey();
            String rank = entry.getValue();
            int gamemodeColor = GAMEMODE_COLORS.getOrDefault(gamemode, 0xFFFFFFFF);
            
            String displayText = gamemode.substring(0, 1).toUpperCase() + gamemode.substring(1) + ": " + rank;
            renderText(matrix, buffer, displayText, 0, yOffset, gamemodeColor, false);
            
            yOffset += 10;
            count++;
        }
        
        matrices.pop();
    }
    
    private void renderText(Matrix4f matrix, BufferBuilder buffer, String text, float x, float y, int color, boolean shadow) {
        MinecraftClient client = MinecraftClient.getInstance();
        TextRenderer textRenderer = client.textRenderer;
        
        float alpha = (float)(color >> 24 & 0xFF) / 255.0f;
        float red = (float)(color >> 16 & 0xFF) / 255.0f;
        float green = (float)(color >> 8 & 0xFF) / 255.0f;
        float blue = (float)(color & 0xFF) / 255.0f;
        
        VertexConsumerProvider.Immediate immediate = VertexConsumerProvider.immediate(buffer);
        
        if (shadow) {
            textRenderer.draw(text, x + 1, y + 1, 0x80000000, false, matrix, immediate, TextRenderer.TextLayerType.NORMAL, 0, 0xF000F0);
        }
        
        textRenderer.draw(text, x, y, color, false, matrix, immediate, TextRenderer.TextLayerType.NORMAL, 0, 0xF000F0);
        
        immediate.draw();
    }
    
    public static int getRankColor(String rank) {
        return RANK_COLORS.getOrDefault(rank, 0xFFFFFFFF);
    }
    
    public static int getGamemodeColor(String gamemode) {
        return GAMEMODE_COLORS.getOrDefault(gamemode.toLowerCase(), 0xFFFFFFFF);
    }
}
