using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Vid2Notes.Api.Data.Migrations
{
    public partial class AddMidiOutput : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "MidiKey",
                table: "Jobs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "NoteCount",
                table: "Jobs",
                type: "integer",
                nullable: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "MidiKey",
                table: "Jobs");

            migrationBuilder.DropColumn(
                name: "NoteCount",
                table: "Jobs");
        }
    }
}
