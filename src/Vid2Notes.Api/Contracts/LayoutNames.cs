using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Contracts;

public static class LayoutNames
{
    public static SheetLayout Parse(string value) =>
        string.Equals(value, "scroll", StringComparison.OrdinalIgnoreCase) ? SheetLayout.Scroll : SheetLayout.Pages;

    public static string ToName(SheetLayout layout) => layout == SheetLayout.Scroll ? "scroll" : "pages";
}
