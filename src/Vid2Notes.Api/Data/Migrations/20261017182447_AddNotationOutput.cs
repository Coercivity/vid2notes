using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Vid2Notes.Api.Data.Migrations
{
    public partial class AddNotationOutput : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "KeyName",
                table: "Jobs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MusicXmlKey",
                table: "Jobs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "Tempo",
                table: "Jobs",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "TimeSignature",
                table: "Jobs",
                type: "text",
                nullable: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "KeyName",
                table: "Jobs");

            migrationBuilder.DropColumn(
                name: "MusicXmlKey",
                table: "Jobs");

            migrationBuilder.DropColumn(
                name: "Tempo",
                table: "Jobs");

            migrationBuilder.DropColumn(
                name: "TimeSignature",
                table: "Jobs");
        }
    }
}
