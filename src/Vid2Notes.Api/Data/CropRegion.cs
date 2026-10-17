using Vid2Notes.Api.Contracts;

namespace Vid2Notes.Api.Data;

public class CropRegion
{
    public double X { get; set; }
    public double Y { get; set; }
    public double Width { get; set; }
    public double Height { get; set; }

    public static CropRegion From(CropMessage message) => new()
    {
        X = message.X,
        Y = message.Y,
        Width = message.Width,
        Height = message.Height
    };

    public CropMessage ToMessage() => new(X, Y, Width, Height);

    public CropRegion Copy() => new() { X = X, Y = Y, Width = Width, Height = Height };
}
