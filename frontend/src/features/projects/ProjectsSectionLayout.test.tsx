import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsSectionLayout } from "./ProjectsSectionLayout";
import type { NavTreeNode } from "@/api/reports";
import { TooltipProvider } from "@/design-system";
import { useSidebarStore } from "@/store/sidebarStore";

// Team 4 > RWCA: the tree ends at the sub-workspace (AFIT, 26 Oct 2026). RWCA still carries a
// project, as an older server would send it: the tree does not show it.
const tree: NavTreeNode[] = [
  {
    id: "ws-4",
    type: "workspace",
    label: "Team 4",
    team_id: 4,
    board_query: { team: 4 },
    children: [
      {
        id: "ws-4-sub-5",
        type: "sub_workspace",
        label: "RWCA",
        client_id: 5,
        board_query: { team: 4, client: 5 },
        children: [{ id: "project-9", type: "project", label: "Hedwig Group", project_key: "Hedwig", children: [] }],
      },
      { id: "ws-4-sub-6", type: "sub_workspace", label: "Acme", client_id: 6, board_query: { team: 4, client: 6 }, children: [] },
    ],
  },
  { id: "ws-2", type: "workspace", label: "Team 2", team_id: 2, board_query: { team: 2 }, children: [] },
];

vi.mock("@/api/reports", () => ({
  useNavTree: () => ({ data: tree, isLoading: false }),
}));
vi.mock("./CreateClientDialog", () => ({
  CreateClientDialog: (props: { open: boolean; defaultTeamId?: number }) =>
    props.open ? <div role="dialog">New sub-workspace in {props.defaultTeamId ?? "nowhere"}</div> : null,
}));

function Where() {
  const { pathname, search } = useLocation();
  return <div data-testid="where">{`${pathname}${search}`}</div>;
}

function renderTree(at = "/projects") {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/projects" element={<ProjectsSectionLayout />}>
            <Route index element={<Where />} />
            <Route path="*" element={<Where />} />
          </Route>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("Projects tree: Workspace > Sub-workspace, each opening its tasks", () => {
  beforeEach(() => useSidebarStore.setState((s) => ({ open: { ...s.open, projectsTree: true } })));

  it("stops at the sub-workspace", async () => {
    renderTree();
    expect(screen.getByText("Workspace › Sub-workspace")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Team 4"));
    expect(screen.getByText("RWCA")).toBeInTheDocument();
    await userEvent.click(screen.getByText("RWCA"));
    expect(screen.queryByText("Hedwig Group")).not.toBeInTheDocument(); // no projects below it
    expect(screen.queryByRole("button", { name: "Expand RWCA" })).not.toBeInTheDocument();
  });

  it("a workspace opens its tasks and expands; a sub-workspace opens them filtered by workspace and itself", async () => {
    renderTree();
    await userEvent.click(screen.getByText("Team 4"));
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/all-issues?team=4");
    expect(screen.getByText("RWCA")).toBeInTheDocument(); // expanded too
    await userEvent.click(screen.getByText("RWCA"));
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/all-issues?team=4&client=5");
    await userEvent.click(screen.getByText("Team 2")); // nothing in it, still opens
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/all-issues?team=2");
  });

  it("keeps the view (Kanban, Tasks or Summary) and shows which row is open", async () => {
    renderTree("/projects/all-issues?team=4&view=summary");
    expect(screen.getByText("Team 4").closest("[aria-current]")).toHaveAttribute("aria-current", "true");
    await userEvent.click(screen.getByRole("button", { name: "Expand Team 4" }));
    await userEvent.click(screen.getByText("Acme"));
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/all-issues?team=4&client=6&view=summary");
    expect(screen.getByText("Acme").closest("[aria-current]")).toHaveAttribute("aria-current", "true");
  });

  it("the arrow only expands or collapses", async () => {
    renderTree();
    await userEvent.click(screen.getByRole("button", { name: "Expand Team 4" }));
    expect(screen.getByText("RWCA")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/projects"); // did not open
    expect(screen.getByTestId("where")).not.toHaveTextContent("all-issues");
    await userEvent.click(screen.getByRole("button", { name: "Collapse Team 4" }));
    expect(screen.queryByText("RWCA")).not.toBeInTheDocument();
  });

  it("adds a sub-workspace to a workspace from its row; projects can't be created", async () => {
    renderTree();
    await userEvent.click(screen.getByRole("button", { name: "New sub-workspace in Team 4" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("New sub-workspace in 4");
    expect(screen.getByTestId("where")).not.toHaveTextContent("all-issues"); // the row's button does not open it
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByText("Team 4"));
    expect(screen.queryByRole("button", { name: /New project/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create/ })).not.toBeInTheDocument();
  });

  it("finds a sub-workspace by name", async () => {
    renderTree();
    await userEvent.type(screen.getByRole("textbox", { name: "Search workspaces and sub-workspaces" }), "acme");
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.queryByText("RWCA")).not.toBeInTheDocument();
  });
});
