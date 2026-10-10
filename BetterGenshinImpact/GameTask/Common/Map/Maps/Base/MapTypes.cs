using System;
using System.ComponentModel;

namespace BetterGenshinImpact.GameTask.Common.Map.Maps.Base;

public enum MapTypes
{
    [Description("提瓦特大陆")]
    Teyvat,

    [Description("层岩巨渊")]
    TheChasm,

    [Description("渊下宫")]
    Enkanomiya,

    [Description("旧日之海")]
    SeaOfBygoneEras,

    [Description("远古圣山")]
    AncientSacredMountain,

    [Description("空之神殿")]
    TempleOfSpace,

    [Description("霜月")]
    MoonCanon,
}
public static class MapTypesExtensions
{
    public static MapTypes ParseFromDescription(string description)
    {
        foreach (var field in typeof(MapTypes).GetFields())
        {
            if (Attribute.GetCustomAttribute(field, typeof(DescriptionAttribute)) is DescriptionAttribute attribute)
            {
                if (attribute.Description == description)
                {
                    return (MapTypes)field.GetValue(null)!;
                }
            }
        }
        throw new ArgumentException($"No enum value found with the description '{description}'", nameof(description));
    }
    
    public static MapTypes ParseFromName(string name)
    {
        if (Enum.TryParse<MapTypes>(name, true, out var result))
        {
            return result;
        }
        throw new ArgumentException($"No enum value found with the name '{name}'", nameof(name));
    }
}
