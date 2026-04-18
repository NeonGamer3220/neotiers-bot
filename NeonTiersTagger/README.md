# NeonTiersTagger

A Minecraft Fabric mod that displays player ranks from the [NeoTiers](https://neontiers.vercel.app) tierlist above player heads in-game.

## Features

- **Rank Display**: Shows player ranks (HT1-LT5) above their heads
- **Color Coding**: Different colors for different rank tiers
- **Points Display**: Shows total points earned across all gamemodes
- **Gamemode Ranks**: Displays top 3 gamemode-specific ranks
- **Real-time Updates**: Fetches rank data from the NeoTiers API
- **Configurable**: Customize display options via config file

## Supported Gamemodes

- Vanilla
- UHC
- Pot
- NethPot
- SMP
- Sword
- Axe
- Mace
- Cart
- Creeper
- DiaSMP
- OGVanilla
- ShieldlessUHC
- SpearMace
- SpearElytra

## Rank Colors

### HT Ranks (Gold/Yellow tones)
- **HT1**: Gold
- **HT2**: Orange
- **HT3**: Dark Orange
- **HT4**: Peru
- **HT5**: Tan

### LT Ranks (Silver/Blue tones)
- **LT1**: Silver
- **LT2**: Dark Gray
- **LT3**: Sky Blue
- **LT4**: Steel Blue
- **LT5**: Cadet Blue

## Installation

1. Install [Fabric Loader](https://fabricmc.net/use/installer/) for Minecraft 1.20.1
2. Download the latest release from the releases page
3. Place the `.jar` file in your `.minecraft/mods` folder
4. Install [Fabric API](https://modrinth.com/mod/fabric-api) if you haven't already

## Building from Source

### Prerequisites
- Java 17 or higher
- Git

### Steps

1. Clone the repository:
```bash
git clone https://github.com/neontiers/neontiers-tagger.git
cd neontiers-tagger
```

2. Build the mod:
```bash
./gradlew build
```

3. The compiled mod will be in `build/libs/`

## Configuration

The mod creates a configuration file at `config/neontiers-tagger.properties` with the following options:

| Option | Default | Description |
|--------|---------|-------------|
| `apiUrl` | `https://neontiers.vercel.app/api/tests` | NeoTiers API endpoint |
| `showRanks` | `true` | Display rank tags |
| `showPoints` | `true` | Display total points |
| `showGamemodes` | `true` | Display gamemode-specific ranks |
| `maxGamemodesDisplayed` | `3` | Maximum gamemodes to display |
| `enableCache` | `true` | Enable API response caching |
| `cacheDurationSeconds` | `30` | Cache duration in seconds |

## API Integration

This mod integrates with the NeoTiers API to fetch player rank data. The API endpoint returns test results in the following format:

```json
{
  "tests": [
    {
      "username": "PlayerName",
      "gamemode": "Sword",
      "rank": "HT3",
      "points": 8
    }
  ]
}
```

## Commands

- `/neontiers reload` - Reload configuration
- `/neontiers cache clear` - Clear rank cache
- `/neontiers api <url>` - Set custom API URL

## Dependencies

- Minecraft 1.20.1
- Fabric Loader 0.14.22+
- Fabric API 0.87.0+
- Gson 2.10.1

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Links

- [NeoTiers Website](https://neontiers.vercel.app)
- [Discord Server](https://discord.gg/neontiers)
- [GitHub Repository](https://github.com/neontiers/neontiers-tagger)

## Support

For issues, suggestions, or questions, please open an issue on GitHub or contact us on Discord.
