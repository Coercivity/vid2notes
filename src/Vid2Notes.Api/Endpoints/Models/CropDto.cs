using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Endpoints.Models;

public record CropDto(double X, double Y, double Width, double Height)
{
    public static CropDto? From(CropRegion? crop) =>
        crop is null ? null : new CropDto(crop.X, crop.Y, crop.Width, crop.Height);

    public CropRegion ToRegion() => new() { X = X, Y = Y, Width = Width, Height = Height };
}
