import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Dashboard } from "./Dashboard";

describe("Dashboard Page", () => {
  test("renders Gateway header and active user profile input", () => {
    render(<Dashboard />);
    expect(screen.getByText("Device Trust Gateway")).toBeInTheDocument();
    expect(screen.getByText("My Approved Devices")).toBeInTheDocument();
  });

  test("allows updating active user email for simulation", () => {
    render(<Dashboard />);
    const input = screen.getByDisplayValue("student@example.com") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "admin@example.com" } });
    expect(input.value).toBe("admin@example.com");
  });

  test("displays navigation portals for chaining, network, and admin", () => {
    render(<Dashboard />);
    expect(screen.getByText("Trust Chaining Portal")).toBeInTheDocument();
    expect(screen.getByText("Campus Wi-Fi Approval")).toBeInTheDocument();
    expect(screen.getByText("Admin Configurations")).toBeInTheDocument();
  });
});
