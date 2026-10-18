using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Contracts;

public static class LayoutNames
{
    public static SheetLayout Parse(string value) => value.ToLowerInvariant() switch
    {
        "scroll" => SheetLayout.Scroll,
        "synthesia" => SheetLayout.Synthesia,
        _ => SheetLayout.Pages
    };

    public static string ToName(SheetLayout layout) => layout switch
    {
        SheetLayout.Scroll => "scroll",
        SheetLayout.Synthesia => "synthesia",
        _ => "pages"
    };
}
