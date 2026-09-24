import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, endpoints } from './api'
import type { OperationalContext } from './types'

type ContextValue = {
  contexts: OperationalContext[]
  active: OperationalContext | null
  activeSimulationId: string
  selectSimulation: (id:string)=>void
  resolveAndSelect: (id:string)=>Promise<OperationalContext>
  loading: boolean
  error: Error | null
}

const OperationalSessionContext=createContext<ContextValue|null>(null)
const STORAGE_KEY='aigatos.activeSimulationId'

export function OperationalSessionProvider({children}:{children:ReactNode}){
  const queryClient=useQueryClient()
  const query=useQuery({queryKey:['contexts','all'],queryFn:()=>apiGet<OperationalContext[]>(endpoints.contexts('all')),refetchInterval:q=>(q.state.data?.some(item=>!['COMPLETED','FAILED','APPROVED','REJECTED'].includes(item.simulation_status))?15_000:false)})
  const [activeSimulationId,setActiveSimulationId]=useState(()=>localStorage.getItem(STORAGE_KEY)??'')
  useEffect(()=>{
    if(!query.data?.length)return
    if(query.data.some(item=>item.simulation_id===activeSimulationId))return
    const preferred=query.data.find(item=>item.source==='LIVE_SIMULATION')??query.data[0]
    setActiveSimulationId(preferred.simulation_id)
  },[query.data,activeSimulationId])
  useEffect(()=>{if(activeSimulationId)localStorage.setItem(STORAGE_KEY,activeSimulationId)},[activeSimulationId])
  const resolveAndSelect=async(id:string)=>{
    const resolved=await apiGet<OperationalContext>(endpoints.simulationContext(id))
    queryClient.setQueryData<OperationalContext[]>(['contexts','all'],current=>[
      resolved,...(current??[]).filter(item=>item.simulation_id!==id),
    ])
    setActiveSimulationId(id)
    return resolved
  }
  const resolvedSimulationId=activeSimulationId||((query.data?.find(item=>item.source==='LIVE_SIMULATION')??query.data?.[0])?.simulation_id??'')
  const value=useMemo<ContextValue>(()=>({
    contexts:query.data??[],
    active:query.data?.find(item=>item.simulation_id===resolvedSimulationId)??null,
    activeSimulationId:resolvedSimulationId,
    selectSimulation:setActiveSimulationId,
    resolveAndSelect,
    loading:query.isLoading,
    error:query.error,
  }),[query.data,query.isLoading,query.error,activeSimulationId,resolvedSimulationId])
  return <OperationalSessionContext.Provider value={value}>{children}</OperationalSessionContext.Provider>
}

export function useOperationalSession(){
  const value=useContext(OperationalSessionContext)
  if(!value)throw new Error('OperationalSessionProvider is missing')
  return value
}
