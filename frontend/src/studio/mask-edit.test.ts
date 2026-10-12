import { describe, expect, it } from "vitest";
import { maskPoint, polygonArea } from "./mask-edit";

describe("source mask coordinates", () => {
  it("maps display coordinates independently of source resolution", () => {
    expect(maskPoint(150,100,{left:50,top:50,width:200,height:100},4000,2000)).toEqual({x:2000,y:1000});
    expect(maskPoint(-10,500,{left:0,top:0,width:100,height:100},400,200)).toEqual({x:0,y:199});
  });
  it("rejects degenerate polygons", () => {
    expect(polygonArea([{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:0,y:10}])).toBe(100);
    expect(polygonArea([{x:0,y:0},{x:10,y:0}])).toBe(0);
  });
});
